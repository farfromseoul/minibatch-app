"""검토와 승인 (아키텍처 흐름 2, D24).

승인은 기록만 한다. YouTube 공개 전환(videos.update)은 작업 순서 20-d 에서 publish 모듈이 하고,
그때도 approved_at 이 없으면 호출하지 않는다 (성공 기준 5).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.timeutil import to_utc_naive
from app.db.models import Episode, Job, Publication, Series

from .status import set_status


def _episode(s: Session, job: Job) -> Optional[Episode]:
    if not job.series_id:
        return None
    return s.scalar(select(Episode).where(Episode.series_id == job.series_id, Episode.number == job.episode_number))


def approve(s: Session, settings, job: Job, now: datetime, approved_by: str, publish_at: Optional[datetime]) -> None:
    if job.status != "REVIEW":
        raise ApiError(409, "not_in_review", f"검토 대기(REVIEW)에서만 승인한다. 지금: {job.status}")
    pub = s.get(Publication, job.id) or Publication(job_id=job.id, platform="youtube", visibility="private")
    pub.approved_by = approved_by
    pub.approved_at = now
    pub.publish_at = to_utc_naive(publish_at) if publish_at else None
    s.add(pub)
    set_status(s, job, "APPROVED", now, actor=approved_by)
    ep = _episode(s, job)
    if ep is not None:
        ep.status = "APPROVED"
        ep.summary, ep.next_teaser = _story_from_script(settings, job.id)
        _finish_series_if_done(s, job.series_id)


def reject(s: Session, job: Job, now: datetime, rejected_by: str, reason: str) -> None:
    if job.status != "REVIEW":
        raise ApiError(409, "not_in_review", f"검토 대기(REVIEW)에서만 반려한다. 지금: {job.status}")
    set_status(s, job, "REJECTED", now, actor=rejected_by, reason=reason)
    ep = _episode(s, job)
    if ep is not None:
        ep.status = "REJECTED"
        series = s.get(Series, job.series_id)
        series.status = "PAUSED"  # 반려된 화를 전제로 다음 화를 만들지 않는다 (D24)


def _story_from_script(settings, job_id: str) -> tuple[Optional[str], Optional[str]]:
    """script 단계가 쓴 이번 화 요약·다음 화 예고. 다음 화 대본의 입력이 된다."""
    path = settings.jobs_dir / job_id / "script.json"
    if not path.is_file():
        return None, None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("episodeSummary"), data.get("nextTeaser")


def _finish_series_if_done(s: Session, series_id: str) -> None:
    statuses = s.scalars(select(Episode.status).where(Episode.series_id == series_id)).all()
    if statuses and all(st == "APPROVED" for st in statuses):
        s.get(Series, series_id).status = "DONE"
