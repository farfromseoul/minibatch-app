"""주제 후보·시리즈 계획 자동 생성 (아키텍처 D25). 결과는 PROPOSED 로 저장하고 사용자가 승인해야 쓴다."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.timeutil import kst_date
from app.db.models import Episode, Job, Series, Topic
from app.llm.base import LlmEngine, LlmError
from app.llm.converse import converse
from app.llm.prompting import render, render_messages

from . import series_order
from .series import KEY
from .text import normalize_topic


def _category(settings, key: str) -> dict[str, Any]:
    import yaml

    path = settings.category_file(key)
    if not path.is_file():
        raise ApiError(400, "unknown_category", f"카테고리 설정이 없다: {key}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _ask(llm: LlmEngine, prompt, schema: dict, name: str, check) -> Any:
    """prompt 는 user 문자열 하나 또는 [system, user] 메시지 목록"""
    messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]
    try:
        out = converse(llm, messages, schema, name, check)
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


def next_series_key(s: Session, now: datetime) -> str:
    """제목·key 없이 자동으로 만드는 시리즈의 key: s<한국 날짜>-<그날 순번> (D27)"""
    prefix = f"s{kst_date(now)}-"
    ids = s.scalars(select(Series.id).where(Series.id.like(prefix + "%"))).all()
    n = max((int(i.rsplit("-", 1)[1]) for i in ids if i.rsplit("-", 1)[1].isdigit()), default=0) + 1
    return f"{prefix}{n}"


def generate_series_plan(s: Session, settings, now: datetime, llm: LlmEngine, *, key: str, category: str,
                         title: Optional[str], count: int, bible: Optional[dict[str, Any]]) -> Series:
    """title 이 없으면 LLM 이 제목도 정한다(D27 자동 운영). 예전 시리즈 제목을 주어 겹치지 않게 한다"""
    cat = _category(settings, category)
    if not KEY.match(key):
        raise ApiError(422, "invalid_request", "key 는 영문 소문자·숫자·- 64자 이내")
    if s.get(Series, key) is not None:
        raise ApiError(409, "series_exists", f"같은 key 의 시리즈가 있다: {key}")
    recent = list(s.scalars(select(Series.title).order_by(Series.created_at.desc()).limit(30)))
    used = _used_topics(s)
    used_keys = {normalize_topic(t) for t in used}
    messages, _ = render_messages("series_plan", count=count, category_title=cat.get("title", category),
                       audience=cat.get("audience", ""),
                       title_line=f"'{title}'이라는" if title else "새",
                       title_rule="" if title else "- title: 시리즈 제목 한 줄. 아래 예전 시리즈와 주제·인물이 겹치지 않게\n",
                       recent="" if title or not recent else "예전 시리즈 제목:\n" + "\n".join(f"- {t}" for t in recent) + "\n",
                       given_bible=f"사용자가 정한 설정(그대로 쓴다): {json.dumps(bible, ensure_ascii=False)}" if bible else "",
                       continuity=_continuity(s), used_topics="\n".join(f"- {t}" for t in used) or "- (없음)")
    st = {"type": "string"}
    schema = {"type": "object", "properties": {
        # 2026-10-17: 가상 인물(characters)을 없앴다. 진행자 한 명의 연속 강의형 (오글거림·이해 방해)
        "bible": {"type": "object", "properties": {"premise": st, "tone": st},
                  "required": ["premise", "tone"], "additionalProperties": False},
        "episodes": {"type": "array", "items": {"type": "object", "properties": {"title": st, "outline": st},
                                                "required": ["title", "outline"], "additionalProperties": False},
                     "minItems": count, "maxItems": count}},
        "required": ["bible", "episodes"], "additionalProperties": False}
    if not title:
        schema["properties"] = {"title": st, **schema["properties"]}
        schema["required"] = ["title", "bible", "episodes"]

    def check(d: Any) -> list[str]:
        if not isinstance(d, dict) or not isinstance(d.get("episodes"), list) or not isinstance(d.get("bible"), dict):
            return ["bible 객체와 episodes 배열이 필요하다"]
        if len(d["episodes"]) != count:
            return [f"episodes 는 정확히 {count}개여야 한다 (지금 {len(d['episodes'])}개)"]
        if any(not e.get("title") or not e.get("outline") for e in d["episodes"]):
            return ["화마다 title 과 outline 이 필요하다"]
        if not title and not str(d.get("title") or "").strip():
            return ["시리즈 title 이 필요하다"]
        repeats = [f"{i}화 '{e['title']}'" for i, e in enumerate(d["episodes"], start=1)
                   if normalize_topic(str(e["title"])) in used_keys]
        if repeats:  # D33: 이미 다룬 주제는 중복 검사에 걸려 그 화를 만들 수 없다 (2026-10-18 실제)
            return [f"{', '.join(repeats)} 는 이미 다룬 주제다. 이미 다룬 주제 목록과 겹치지 않는 새 개념으로 바꾼다"]
        return []

    data = _ask(llm, messages, schema, "series_plan", check)
    series = Series(id=key, category=category, title=(title or str(data["title"]).strip())[:200], bible=bible or data["bible"], plan_source="llm",
                    status="PROPOSED", created_at=now, approved_at=None)
    s.add(series)
    s.flush()  # 화보다 시리즈를 먼저 넣는다 (부록 B: 저장 순서)
    for i, e in enumerate(data["episodes"], start=1):  # 번호는 코드가 매긴다
        s.add(Episode(series_id=key, number=i, title=e["title"], outline=e["outline"], status="PLANNED"))
    return series


def _used_topics(s: Session, limit: int = 200) -> list[str]:
    """다시 다루면 안 되는 주제: 취소하지 않은 작업의 주제와, 순번 안 시리즈의 화 제목 (D33)"""
    topics = list(s.scalars(select(Job.topic).where(Job.status != "CANCELLED").order_by(Job.created_at.desc()).limit(limit)))
    for series in series_order.ordered(s):
        topics += list(s.scalars(select(Episode.title).where(Episode.series_id == series.id).order_by(Episode.number)))
    seen, out = set(), []
    for t in topics:
        if normalize_topic(t) not in seen:
            seen.add(normalize_topic(t))
            out.append(t)
    return out


def _continuity(s: Session) -> str:
    """몇 번째 시리즈인지와 이어받을 바로 앞 시리즈 (D33: 앞 시리즈와 연관되게, 겹치지 않게)"""
    n = series_order.next_sequence(s)
    prev = series_order.previous(s)
    if prev is None:
        return f"이번이 {n}번째 시리즈다(첫 시리즈)."
    eps = s.scalars(select(Episode).where(Episode.series_id == prev.id).order_by(Episode.number)).all()
    lines = "\n".join(f"- {e.number}화 {e.title}" for e in eps)
    premise = (prev.bible or {}).get("premise", "")
    return (f"이번이 {n}번째 시리즈다. 바로 앞 {series_order.label(s, prev)}(전제: {premise})에서 다룬 화:\n{lines}\n"
            "이번 시리즈는 앞 시리즈를 본 시청자가 다음으로 궁금해할 주제로 잡는다: 앞 시리즈에서 배운 개념을 바탕으로 "
            "한 단계 더 깊은 원리나 그 개념이 쓰이는 다음 영역으로 잇는다. 앞 시리즈의 개념을 다시 설명하는 화는 만들지 않는다.")


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
