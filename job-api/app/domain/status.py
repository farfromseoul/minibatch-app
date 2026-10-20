"""작업 상태 바꾸기. 상태는 job-api 만 바꾸고, 바꿀 때마다 job_event 에 남긴다 (아키텍처 "상태 모델")."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import Job, JobEvent

RUNNABLE = {"PENDING", "RUNNING", "WAITING"}  # 단계를 요청할 수 있는 상태
# 끝난 화: 승인(공개)됐거나, 검토를 넘지 못해 건너뛴 화 (2026-10-21). 다음 화 만들기·승인·업로드 순서·시리즈 완료가 같이 쓴다
EP_DONE = ("APPROVED", "SKIPPED")
RESETTABLE = {"PENDING", "RUNNING", "WAITING", "FAILED", "REVIEW", "REJECTED"}


def set_status(s: Session, job: Job, to: str, now: datetime, actor: str = "job-api",
               reason: Optional[str] = None) -> None:
    if job.status == to and reason is None:
        return
    s.add(JobEvent(job_id=job.id, from_status=job.status, to_status=to, actor=actor, reason=reason, at=now))
    job.status = to
    job.updated_at = now
