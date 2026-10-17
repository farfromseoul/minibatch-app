"""취소 (아키텍처 D29, 2026-10-17).

작업 취소: 공개 전 작업을 CANCELLED 로 바꾼다. 다시 실행·되돌리기를 하지 않는다. 이미 비공개로 올린 영상은 지우지 않는다.
시리즈 화를 취소하면 그 화도 CANCELLED, 시리즈는 PAUSED (그 화 없이는 다음 화를 만들 수 없다). resume 하면 그 화부터 다시.
시리즈 취소: 시리즈를 CANCELLED 로. 승인되지 않은 화와 공개 전 작업도 CANCELLED. 승인·공개된 화는 그대로 둔다.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import Episode, Job, Series

from .status import set_status

CANCELLABLE_JOB = {"PENDING", "RUNNING", "WAITING", "FAILED", "REVIEW", "REJECTED"}  # 아직 공개 전


def cancel_job(s: Session, job: Job, now: datetime, who: str, reason: str) -> None:
    if job.status not in CANCELLABLE_JOB:
        raise ApiError(409, "not_cancellable", f"공개 전 작업만 취소한다. 지금: {job.status} (공개된 영상은 Studio 에서 비공개로)")
    set_status(s, job, "CANCELLED", now, actor=who, reason=reason)
    if not job.series_id:
        return
    ep = s.scalar(select(Episode).where(Episode.series_id == job.series_id, Episode.number == job.episode_number))
    if ep is not None and ep.status != "APPROVED":
        ep.status = "CANCELLED"
        series = s.get(Series, job.series_id)
        if series.status in ("APPROVED", "ACTIVE"):
            series.status = "PAUSED"


def cancel_series(s: Session, series: Series, now: datetime, who: str, reason: str) -> None:
    if series.status in ("DONE", "CANCELLED"):
        raise ApiError(409, "not_cancellable", f"끝났거나 이미 취소된 시리즈다: {series.status}")
    for ep in s.scalars(select(Episode).where(Episode.series_id == series.id)):
        if ep.status == "APPROVED":
            continue  # 승인(공개)된 화는 그대로
        job = s.get(Job, ep.job_id) if ep.job_id else None
        if job is not None and job.status in CANCELLABLE_JOB:
            set_status(s, job, "CANCELLED", now, actor=who, reason=f"시리즈 취소: {reason}")
        ep.status = "CANCELLED"
    series.status = "CANCELLED"
