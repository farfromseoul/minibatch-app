"""주제 후보 (기획서 F1a, 아키텍처 D25). 사용자 주제는 READY, 자동 생성 주제는 PROPOSED 로 들어온다."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import Topic

from .jobs import ensure_category
from .text import normalize_topic


def add_user_topics(s: Session, settings, now: datetime, category: str, titles: list[str]) -> int:
    ensure_category(settings, category)
    created = 0
    seen: set[str] = set()
    for title in titles:
        key = normalize_topic(title)
        if not key or key in seen or s.scalar(select(Topic.id).where(Topic.normalized_key == key)):
            continue
        seen.add(key)
        s.add(Topic(title=title.strip(), normalized_key=key, category=category, source="user",
                    status="READY", created_at=now))
        created += 1
    return created


def decide(topic: Topic, approve: bool) -> None:
    if topic.status != "PROPOSED":
        raise ApiError(409, "topic_not_proposed", f"승인 대기 주제만 정한다. 지금: {topic.status}")
    topic.status = "READY" if approve else "REJECTED"
