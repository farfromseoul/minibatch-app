"""시리즈를 차례대로 (아키텍처 D33, 2026-10-18).

시리즈 순번은 승인 순서다(취소한 시리즈는 세지 않는다). 앞 시리즈의 모든 화가 만들어져야 다음 시리즈 1화를 만들고,
다음 시리즈 1화의 승인(공개)·업로드는 앞 시리즈가 끝난 뒤에 한다. 화 순서(D24·D31)를 시리즈 사이로 넓힌 것이다.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Episode, Job, Publication, Series

from .status import EP_DONE

# 순번을 매기는 시리즈: 승인된 뒤의 상태. 취소(CANCELLED)·승인 대기(PROPOSED)는 세지 않는다
COUNTED = ("APPROVED", "ACTIVE", "PAUSED", "DONE")
PRODUCED = ("REVIEW", "APPROVED", "SCHEDULED", "PUBLISHED")  # jobs.PRODUCED 와 같다 (순환 import 를 피해 둔다)


def ordered(s: Session) -> list[Series]:
    return list(s.scalars(select(Series).where(Series.status.in_(COUNTED), Series.approved_at.is_not(None))
                          .order_by(Series.approved_at, Series.id)))


def sequence(s: Session, series: Series) -> Optional[int]:
    """몇 번째 시리즈인지 (1부터). 순번 밖이면 None"""
    ids = [x.id for x in ordered(s)]
    return ids.index(series.id) + 1 if series.id in ids else None


def next_sequence(s: Session) -> int:
    return len(ordered(s)) + 1


def previous(s: Session, series: Optional[Series] = None) -> Optional[Series]:
    """series 바로 앞 시리즈. series 가 없으면(새 계획) 가장 최근 시리즈"""
    items = ordered(s)
    if series is None:
        return items[-1] if items else None
    ids = [x.id for x in items]
    if series.id not in ids:
        return items[-1] if items else None
    i = ids.index(series.id)
    return items[i - 1] if i > 0 else None


def label(s: Session, series: Series) -> str:
    n = sequence(s, series)
    return f"{n}번째 시리즈 '{series.title}'" if n else f"시리즈 '{series.title}'"


def _episodes(s: Session, series: Series) -> list[Episode]:
    return list(s.scalars(select(Episode).where(Episode.series_id == series.id).order_by(Episode.number)))


def _made(s: Session, ep: Episode) -> bool:
    if ep.status in EP_DONE:
        return True
    job = s.get(Job, ep.job_id) if ep.job_id else None
    if job is None:
        return False
    return job.status in PRODUCED or (job.status in ("PENDING", "RUNNING", "WAITING") and job.current_step == "upload")


def production_blocker(s: Session, series: Series) -> Optional[str]:
    """이 시리즈 1화를 아직 만들면 안 되는 이유: 앞 시리즈에 다 만들어지지 않은 화가 있다"""
    prev = previous(s, series)
    if prev is None or prev.status == "DONE":
        return None
    for ep in _episodes(s, prev):
        if not _made(s, ep):
            job = s.get(Job, ep.job_id) if ep.job_id else None
            state = job.status if job else ep.status
            return (f"{label(s, prev)} {ep.number}화가 아직 다 만들어지지 않았다({state}). "
                    f"앞 시리즈를 끝낸 뒤 '{series.title}' 1화를 만든다 (D33)")
    return None


def approval_blocker(s: Session, series: Series) -> Optional[str]:
    """이 시리즈 1화를 아직 승인(공개)하면 안 되는 이유: 앞 시리즈가 끝나지(DONE) 않았다"""
    prev = previous(s, series)
    if prev is None or prev.status == "DONE":
        return None
    return f"{label(s, prev)}를 먼저 끝까지 승인한다 (D33)"


def upload_blocker(s: Session, series: Series) -> Optional[str]:
    """이 시리즈 1화를 아직 올리면 안 되는 이유: 앞 시리즈 마지막 화가 YouTube 에 없다"""
    prev = previous(s, series)
    if prev is None or prev.status == "DONE":
        return None
    eps = _episodes(s, prev)
    if not eps:
        return None
    last = eps[-1]
    pub = s.get(Publication, last.job_id) if last.job_id else None
    if last.status in EP_DONE or (pub is not None and pub.video_id):
        return None
    return f"{label(s, prev)} {last.number}화가 아직 업로드되지 않았다. 앞 시리즈를 올린 뒤에 1화를 올린다 (D33)"
