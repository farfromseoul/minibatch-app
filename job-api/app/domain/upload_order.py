"""업로드 대기 중에도 다음 화를 미리 만들고, 업로드는 화 순서대로 (아키텍처 D31, 2026-10-17).

제작은 앞서가도 된다. 업로드만 앞 화가 YouTube 에 올라간 뒤에 한다(재생목록·이전 화 링크 순서).
무엇을 이어 할지(GET /jobs/next)도 여기서 정해, n8n 과 job-api 가 같은 규칙을 쓴다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Episode, Job, Publication, Series, StepRun

from . import series_order

from .status import RUNNABLE


def waiting_for_upload(job: Job) -> bool:
    """qc 까지 끝나고 업로드만 남은 작업 (단계는 순서대로만 돌므로 지금 단계가 upload 면 qc 는 성공했다)"""
    return job.status in RUNNABLE and job.current_step == "upload"


def upload_blocker(s: Session, job: Job) -> Optional[str]:
    """이 작업을 지금 올리면 안 되는 이유. 시리즈 앞 화가 아직 YouTube 에 없으면 그 화를 알린다"""
    if not job.series_id or not job.episode_number:
        return None
    if job.episode_number <= 1:  # 다음 시리즈 1화는 앞 시리즈 마지막 화 뒤에 (D33)
        series = s.get(Series, job.series_id)
        return series_order.upload_blocker(s, series) if series is not None else None
    n = job.episode_number - 1
    prev = s.scalar(select(Episode).where(Episode.series_id == job.series_id, Episode.number == n))
    if prev is not None and prev.status == "APPROVED":
        return None
    pub = s.get(Publication, prev.job_id) if prev is not None and prev.job_id else None
    if pub is not None and pub.video_id:
        return None
    return f"{n}화가 아직 업로드되지 않았다. {n}화를 올린 뒤에 {job.episode_number}화를 올린다 (화 순서)"


def _last_run(s: Session, job: Job) -> Optional[StepRun]:
    return s.scalar(select(StepRun).where(StepRun.job_id == job.id, StepRun.step == job.current_step,
                                          StepRun.superseded.is_(False)).order_by(StepRun.attempt.desc()))


def _wait_reason(s: Session, job: Job, now: datetime) -> Optional[str]:
    if job.status != "WAITING":
        return None
    run = _last_run(s, job)
    if run is None or run.status != "failed":
        return None
    if run.kind == "quota" and run.retry_at:
        retry_at = datetime.strptime(run.retry_at, "%Y-%m-%dT%H:%M:%SZ")
        if retry_at > now:
            return f"업로드 한도 대기, {run.retry_at} 이후 다시"
    if run.kind == "blocked":
        return upload_blocker(s, job)
    return None


def next_job(s: Session, now: datetime) -> dict[str, Any]:
    """이어 할 작업 하나. 기다리는 이유가 남은 작업은 건너뛴다. 없으면 jobId 없음 → n8n 이 새 작업을 만든다"""
    skipped = []
    for job in s.scalars(select(Job).where(Job.status.in_(RUNNABLE)).order_by(Job.created_at, Job.id)):
        reason = _wait_reason(s, job, now)
        if reason is None:
            return {"jobId": job.id, "skipped": skipped}
        skipped.append({"id": job.id, "reason": reason})
    return {"jobId": None, "skipped": skipped}
