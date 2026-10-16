"""주제 후보·시리즈 계획 자동 생성 (아키텍처 D25). 결과는 PROPOSED 로 저장하고 사용자가 승인해야 쓴다."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import Episode, Job, Series, Topic
from app.llm.base import LlmEngine, LlmError
from app.llm.converse import converse
from app.llm.prompting import render

from .series import KEY
from .text import normalize_topic


def _category(settings, key: str) -> dict[str, Any]:
    import yaml

    path = settings.category_file(key)
    if not path.is_file():
        raise ApiError(400, "unknown_category", f"카테고리 설정이 없다: {key}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _ask(llm: LlmEngine, prompt: str, schema: dict, name: str, check) -> Any:
    try:
        out = converse(llm, [{"role": "user", "content": prompt}], schema, name, check)
    except LlmError as e:  # transient
        raise ApiError(503, "llm_unavailable", e.message) from e
    if out.problems:
        raise ApiError(502, "llm_invalid_output", "LLM 응답이 규칙에 맞지 않다: " + "; ".join(out.problems)[:500])
    return out.data


def generate_topics(s: Session, settings, now: datetime, llm: LlmEngine, category: str, count: int) -> list[Topic]:
    cat = _category(settings, category)
    recent = [t for t in s.scalars(select(Topic.title).order_by(Topic.id.desc()).limit(60))]
    recent += [t for t in s.scalars(select(Job.topic).order_by(Job.created_at.desc()).limit(60))]
    prompt, _ = render("topics", category_title=cat.get("title", category), count=count, audience=cat.get("audience", ""),
                       hint=(cat.get("topic_generation") or {}).get("prompt_hint", ""),
                       recent="\n".join(f"- {t}" for t in dict.fromkeys(recent)) or "- (없음)")
    schema = {"type": "object", "properties": {"topics": {"type": "array", "items": {"type": "string"},
                                                          "minItems": 1, "maxItems": count + 3}},
              "required": ["topics"], "additionalProperties": False}
    data = _ask(llm, prompt, schema, "topics",
                lambda d: [] if isinstance(d, dict) and isinstance(d.get("topics"), list) and d["topics"] else ["topics 배열이 필요하다"])
    known = set(s.scalars(select(Topic.normalized_key)))
    created: list[Topic] = []
    for title in data["topics"]:
        key = normalize_topic(title)
        if not key or key in known:  # 이미 있는 주제·응답 안 중복은 뺀다
            continue
        known.add(key)
        topic = Topic(title=title.strip(), normalized_key=key, category=category, source="llm", status="PROPOSED", created_at=now)
        s.add(topic)
        created.append(topic)
        if len(created) >= count:
            break
    return created


def generate_series_plan(s: Session, settings, now: datetime, llm: LlmEngine, *, key: str, category: str, title: str,
                         count: int, bible: Optional[dict[str, Any]]) -> Series:
    cat = _category(settings, category)
    if not KEY.match(key):
        raise ApiError(422, "invalid_request", "key 는 영문 소문자·숫자·- 64자 이내")
    if s.get(Series, key) is not None:
        raise ApiError(409, "series_exists", f"같은 key 의 시리즈가 있다: {key}")
    prompt, _ = render("series_plan", title=title, count=count, category_title=cat.get("title", category),
                       audience=cat.get("audience", ""),
                       given_bible=f"사용자가 정한 설정(그대로 쓴다): {json.dumps(bible, ensure_ascii=False)}" if bible else "")
    st = {"type": "string"}
    schema = {"type": "object", "properties": {
        "bible": {"type": "object", "properties": {
            "premise": st, "tone": st,
            "characters": {"type": "array", "items": {"type": "object", "properties": {"name": st, "role": st},
                                                      "required": ["name", "role"], "additionalProperties": False}}},
                  "required": ["premise", "characters", "tone"], "additionalProperties": False},
        "episodes": {"type": "array", "items": {"type": "object", "properties": {"title": st, "outline": st},
                                                "required": ["title", "outline"], "additionalProperties": False},
                     "minItems": count, "maxItems": count}},
        "required": ["bible", "episodes"], "additionalProperties": False}

    def check(d: Any) -> list[str]:
        if not isinstance(d, dict) or not isinstance(d.get("episodes"), list) or not isinstance(d.get("bible"), dict):
            return ["bible 객체와 episodes 배열이 필요하다"]
        if len(d["episodes"]) != count:
            return [f"episodes 는 정확히 {count}개여야 한다 (지금 {len(d['episodes'])}개)"]
        if any(not e.get("title") or not e.get("outline") for e in d["episodes"]):
            return ["화마다 title 과 outline 이 필요하다"]
        return []

    data = _ask(llm, prompt, schema, "series_plan", check)
    series = Series(id=key, category=category, title=title, bible=bible or data["bible"], plan_source="llm",
                    status="PROPOSED", created_at=now, approved_at=None)
    s.add(series)
    s.flush()  # 화보다 시리즈를 먼저 넣는다 (부록 B: 저장 순서)
    for i, e in enumerate(data["episodes"], start=1):  # 번호는 코드가 매긴다
        s.add(Episode(series_id=key, number=i, title=e["title"], outline=e["outline"], status="PLANNED"))
    return series


def approve_series_plan(s: Session, series: Series, now: datetime, episodes: Optional[list[dict]],
                        bible: Optional[dict[str, Any]]) -> None:
    if series.status != "PROPOSED":
        raise ApiError(409, "series_not_proposed", f"승인 대기 시리즈만 승인한다. 지금: {series.status}")
    if episodes is not None:  # 사용자가 고친 계획으로 바꾼다
        for ep in s.scalars(select(Episode).where(Episode.series_id == series.id)):
            s.delete(ep)
        s.flush()
        for e in episodes:
            s.add(Episode(series_id=series.id, number=e["number"], title=e["title"], outline=e["outline"], status="PLANNED"))
    if bible is not None:
        series.bible = bible
    series.status = "APPROVED"
    series.approved_at = now
