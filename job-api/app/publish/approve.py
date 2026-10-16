"""승인된 작업의 공개 전환 (아키텍처 흐름 2, D9, 성공 기준 5) 과 앞 화 설명란 다음 화 링크 (D26 ④).

승인 기록(publication.approved_at) 검사는 API 경로가 아니라 YouTube 를 부르기 바로 앞(_set_privacy)에 둔다.
어느 경로로 불러도 승인 기록 없이는 공개되지 않게 하기 위해서다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.category import load_category
from app.core.errors import ApiError
from app.db.models import Episode, Job, Publication
from app.domain import review
from app.domain.status import set_status
from app.pipeline.steps.publishing import DEFAULT_DISCLOSURE
from app.youtube.client import YouTubeError


class NotApproved(Exception):
    pass


def _set_privacy(youtube, pub: Publication, privacy: str, publish_at) -> None:
    if pub.approved_at is None or not pub.approved_by:
        raise NotApproved(f"승인 기록이 없다: {pub.job_id}")
    youtube.set_privacy(pub.video_id, privacy, publish_at)


def has_video(s: Session, job: Job) -> bool:
    pub = s.get(Publication, job.id)
    return bool(pub and pub.video_id)


def publish(s: Session, settings, job: Job, youtube_factory: Callable[[Any], Any], now: datetime) -> dict[str, Any]:
    """APPROVED 작업을 공개(또는 예약 공개)한다. YouTube 오류(YouTubeError)는 부른 쪽이 처리한다"""
    if job.status != "APPROVED":
        raise ApiError(409, "not_approved_state", f"승인된(APPROVED) 작업만 공개한다. 지금: {job.status}")
    pub = s.get(Publication, job.id)
    if pub is None or not pub.video_id:
        raise ApiError(409, "no_video", "업로드된 영상이 없다")
    youtube = youtube_factory(settings)
    scheduled = pub.publish_at is not None and pub.publish_at > now
    try:
        if scheduled:  # 예약 공개: 비공개 + publishAt (비공개이고 공개된 적 없는 영상만 된다)
            _set_privacy(youtube, pub, "private", pub.publish_at)
        else:
            _set_privacy(youtube, pub, "public", None)
    except NotApproved as e:
        raise ApiError(409, "not_approved", str(e)) from e
    pub.visibility = "scheduled" if scheduled else "public"
    status = "SCHEDULED" if scheduled else "PUBLISHED"
    set_status(s, job, status, now)
    return {"ok": True, "status": status, "warnings": _link_previous(s, settings, job, youtube, pub.video_id)}


def _link_previous(s: Session, settings, job: Job, youtube, video_id: str) -> list[str]:
    """시리즈 N화가 공개되면 N-1화 설명란(고지 문구 앞)에 다음 화 링크를 단다. 실패해도 공개는 된 것이라 경고만"""
    n = job.episode_number
    if not job.series_id or not n or n < 2:
        return []
    eps = {e.number: e for e in s.scalars(select(Episode).where(Episode.series_id == job.series_id,
                                                                  Episode.number.in_([n - 1, n])))}
    prev = eps.get(n - 1)
    prev_pub = s.get(Publication, prev.job_id) if prev and prev.job_id else None
    if prev_pub is None or not prev_pub.video_id:
        return [f"{n - 1}화 영상이 없어 다음 화 링크를 달지 못했다"]
    disclosure = str((load_category(settings, job.category).get("youtube") or {}).get("disclosure") or DEFAULT_DISCLOSURE).strip()
    title = eps[n].title if n in eps else ""
    text = f"▶ 다음 화: {n}화 {title}\nhttps://www.youtube.com/shorts/{video_id}"
    try:
        youtube.append_to_description(prev_pub.video_id, text, disclosure)
    except YouTubeError as e:
        # 이미 공개됐으므로 publish 를 다시 부르지 않는다(409). 링크는 YouTube Studio 에서 손으로 단다
        return [f"{n - 1}화 설명란에 다음 화 링크를 달지 못했다({e.kind}): {e.message}. Studio 에서 손으로 단다: {text}"]
    return []


def approve_and_publish(s: Session, settings, job: Job, now: datetime, who: str, publish_at,
                        youtube_factory: Callable[[Any], Any]) -> dict[str, Any]:
    """승인을 기록(커밋)하고, 영상이 올라가 있으면 바로 공개 전환한다. YouTube 가 실패해도 승인은 남는다 (APPROVED)"""
    review.approve(s, settings, job, now, who, publish_at)
    s.commit()
    if not has_video(s, job):
        return {"ok": False, "skipped": "업로드된 영상이 없다"}
    try:
        result = publish(s, settings, job, youtube_factory, now)
        s.commit()
        return result
    except YouTubeError as e:
        s.rollback()
        return {"ok": False, "kind": e.kind, "error": e.message}
