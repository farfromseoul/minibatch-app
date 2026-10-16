"""시리즈 (아키텍처 D24·D25)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import Episode, Series

from .jobs import ensure_category

KEY = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def create_user_series(s: Session, settings, now: datetime, *, key: str, category: str, title: str,
                       bible: dict[str, Any], episodes: list[dict[str, Any]]) -> Series:
    """사용자가 화별 계획까지 쓴 시리즈. 바로 APPROVED."""
    ensure_category(settings, category)
    if not KEY.match(key):
        raise ApiError(422, "invalid_request", "key 는 영문 소문자·숫자·- 64자 이내")
    if s.get(Series, key) is not None:
        raise ApiError(409, "series_exists", f"같은 key 의 시리즈가 있다: {key}")
    numbers = [e["number"] for e in episodes]
    if numbers != list(range(1, len(episodes) + 1)):
        raise ApiError(422, "invalid_request", "화 번호는 1부터 빠짐없이 차례대로")
    series = Series(id=key, category=category, title=title, bible=bible, plan_source="user",
                    status="APPROVED", created_at=now, approved_at=now)
    s.add(series)
    s.flush()  # relationship 을 선언하지 않아 저장 순서가 보장되지 않는다. 화보다 시리즈를 먼저 넣는다
    for e in episodes:
        s.add(Episode(series_id=key, number=e["number"], title=e["title"], outline=e["outline"], status="PLANNED"))
    return series


def resume(s: Session, series: Series) -> None:
    if series.status != "PAUSED":
        raise ApiError(409, "series_not_paused", f"멈춘 시리즈만 다시 진행한다. 지금: {series.status}")
    for ep in s.scalars(select(Episode).where(Episode.series_id == series.id, Episode.status == "REJECTED")):
        ep.status = "PLANNED"  # 반려된 화를 다시 만든다
        ep.job_id = None
    series.status = "ACTIVE"


def story_for(s: Session, series_id: str, number: int, keep: int = 3) -> dict[str, Any]:
    """N화 대본의 입력: 시리즈 설정, 앞 화 요약(최근 keep 화), 이번 화·다음 화 계획."""
    series = s.get(Series, series_id)
    eps = {e.number: e for e in s.scalars(select(Episode).where(Episode.series_id == series_id))}
    previous = [{"episode": n, "title": eps[n].title, "summary": eps[n].summary}
                for n in range(max(1, number - keep), number) if n in eps]
    nxt = eps.get(number + 1)
    return {
        "id": series.id,
        "title": series.title,
        "episode": number,
        "totalEpisodes": len(eps),
        "bible": series.bible,
        "previous": previous,
        "outline": eps[number].outline,
        "nextOutline": nxt.outline if nxt else None,
        "nextTitle": nxt.title if nxt else None,  # 끝 장면 "다음 화: 제목" (D26)
    }
