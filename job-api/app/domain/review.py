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

from . import series_order
from .status import set_status


def _episode(s: Session, job: Job) -> Optional[Episode]:
    if not job.series_id:
        return None
    return s.scalar(select(Episode).where(Episode.series_id == job.series_id, Episode.number == job.episode_number))


def approve(s: Session, settings, job: Job, now: datetime, approved_by: str, publish_at: Optional[datetime]) -> None:
    if job.status != "REVIEW":
        raise ApiError(409, "not_in_review", f"검토 대기(REVIEW)에서만 승인한다. 지금: {job.status}")
    ep = _episode(s, job)
    if ep is not None and ep.number > 1:  # 미리 만든 화(D27)도 승인·공개는 화 순서대로
        prev = s.scalar(select(Episode).where(Episode.series_id == job.series_id, Episode.number == ep.number - 1))
        if prev is None or prev.status != "APPROVED":
            raise ApiError(409, "previous_episode_not_approved", f"{ep.number - 1}화를 먼저 승인한다")
    elif ep is not None:  # 다음 시리즈 1화는 앞 시리즈가 끝난 뒤에 공개 (D33)
        blocker = series_order.approval_blocker(s, s.get(Series, job.series_id))
        if blocker:
            raise ApiError(409, "previous_series_not_done", blocker)
    pub = s.get(Publication, job.id) or Publication(job_id=job.id, platform="youtube", visibility="private")
    pub.approved_by = approved_by
    pub.approved_at = now
    pub.publish_at = to_utc_naive(publish_at) if publish_at else None
    s.add(pub)
    set_status(s, job, "APPROVED", now, actor=approved_by)
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
        # 반려된 화를 앞 이야기로 삼아 미리 만든 뒤 화(D27)는 정리한다. resume 하면 반려된 화부터 다시 만든다
        for later in s.scalars(select(Episode).where(Episode.series_id == job.series_id, Episode.number > ep.number,
                                                     Episode.status == "IN_PRODUCTION")):
            later.status = "REJECTED"
            later_job = s.get(Job, later.job_id) if later.job_id else None
            if later_job is not None and later_job.status not in ("APPROVED", "SCHEDULED", "PUBLISHED", "REJECTED"):
                set_status(s, later_job, "REJECTED", now, actor=rejected_by, reason=f"{ep.number}화 반려로 정리 (D27)")


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
