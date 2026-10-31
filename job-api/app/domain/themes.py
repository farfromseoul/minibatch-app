"""목록형 화면 테마 고르기 (D42 v1.3, 2026-10-31).

테마는 카테고리 설정(listicle.yaml `themes`)에 등록한 템플릿이다: 이름·한글 이름·별칭·분위기·어울리는 주제·추천 단어.
render 쪽 테마 파일(render/src/listicle/themes/<이름>.tsx)과 이름이 같아야 한다. 새 테마는 두 곳에 등록만 하면 된다.
추천 = 주제·항목 이름에 추천 단어가 가장 많이 맞는 테마(같으면 설정 순서), 없으면 카테고리 기본 테마(`theme`).
바로 앞 목록형 작업과 같은 테마면 다음 후보로 바꾼다(영상이 단조롭지 않게).
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session


def entries(cat: dict[str, Any]) -> list[dict[str, Any]]:
    return [t for t in cat.get("themes") or [] if isinstance(t, dict) and t.get("name")]


def names(cat: dict[str, Any]) -> list[str]:
    return [str(t["name"]) for t in entries(cat)]


def label(cat: dict[str, Any], name: str) -> str:
    t = next((t for t in entries(cat) if t["name"] == name), None)
    return f"{t.get('label') or name}({name})" if t else name


def resolve(cat: dict[str, Any], word: str) -> Optional[str]:
    """이름(대소문자 무시)이나 별칭 → 테마 이름. 없으면 None"""
    w = word.strip().lower()
    for t in entries(cat):
        if w == str(t["name"]).lower() or w in [str(a).lower() for a in t.get("aliases") or []] or w == str(t.get("label", "")).lower():
            return str(t["name"])
    return None


def recommend(cat: dict[str, Any], topic: str, items: list[str], previous: Optional[str]) -> tuple[str, str]:
    """(테마 이름, 이유)"""
    text = " ".join([topic, *items]).lower()
    scored = []
    for i, t in enumerate(entries(cat)):
        hits = [k for k in t.get("keywords") or [] if str(k).lower() in text]
        scored.append((len(hits), -i, str(t["name"]), hits))
    scored.sort(reverse=True)
    default = str(cat.get("theme") or (scored[-1][2] if scored else "nova"))
    order = [s for s in scored if s[0] > 0] or []
    first = order[0] if order else None
    name, why = (first[2], f"주제에 '{first[3][0]}'") if first else (default, "기본 테마")
    if previous and name == previous:
        others = [s for s in scored if s[2] != previous]
        others.sort(key=lambda s: (s[0], s[1]), reverse=True)
        if others:
            name, why = others[0][2], f"바로 앞 영상이 {previous} 라 바꿈"
    return name, why


def previous_theme(s: Session, exclude_job: Optional[str] = None) -> Optional[str]:
    """가장 최근 목록형 작업의 테마 (작업 입력)"""
    from app.db.models import Job
    q = select(Job).where(Job.category == "listicle").order_by(Job.created_at.desc(), Job.id.desc()).limit(3)
    for job in s.scalars(q):
        if job.id != exclude_job:
            return ((job.input or {}).get("listicle") or {}).get("theme")
    return None
