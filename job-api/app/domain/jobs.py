"""작업 만들기 (기획서 F1·F2, 아키텍처 D15·D24·D25·D27).

주제 출처: 직접 준 주제, 시리즈 다음 화, 자동 선정(시리즈 → 승인된 단독 주제).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.timeutil import kst_date, kst_day_start_utc
from app.db.models import Episode, Job, JobEvent, Series, Topic

from . import series_order
from .status import EP_DONE
from .text import normalize_topic
from .upload_order import waiting_for_upload

INACTIVE = ("FAILED", "REJECTED", "CANCELLED")  # 중복 검사에서 빼는 상태
PRODUCED = ("REVIEW", "APPROVED", "SCHEDULED", "PUBLISHED")  # 다 만들어진 작업 (다음 화를 미리 만들어도 되는 앞 화)


def ensure_category(settings, key: str) -> None:
    if not settings.category_file(key).is_file():
        raise ApiError(400, "unknown_category", f"카테고리 설정이 없다: {key}")


def _next_job_id(s: Session, now: datetime) -> str:
    prefix = f"short-{kst_date(now)}-"
    ids = s.scalars(select(Job.id).where(Job.id.like(prefix + "%"))).all()
    n = max((int(i.rsplit("-", 1)[1]) for i in ids), default=0) + 1
    return f"{prefix}{n:03d}"


def _check_duplicate(s: Session, settings, key: str, now: datetime) -> None:
    since = now - timedelta(days=settings.duplicate_window_days)
    dup = s.scalar(select(Job.id).where(Job.topic_key == key, Job.status.not_in(INACTIVE),
                                        Job.created_at >= since))
    if dup:
        raise ApiError(409, "duplicate_topic", f"최근 {settings.duplicate_window_days}일 안에 같은 주제의 작업이 있다: {dup}")


def _insert(s: Session, settings, now: datetime, *, topic: str, category: str, topic_id: Optional[int] = None,
            series_id: Optional[str] = None, episode_number: Optional[int] = None, extra: Optional[dict] = None) -> Job:
    key = normalize_topic(topic)
    _check_duplicate(s, settings, key, now)
    job = Job(id=_next_job_id(s, now), topic_id=topic_id, topic=topic, topic_key=key, category=category,
              series_id=series_id, episode_number=episode_number, status="PENDING", current_step=None,
              video_engine="remotion", input={"topic": topic, "category": category, **(extra or {})}, created_at=now, updated_at=now)
    s.add(job)
    # relationship 을 선언하지 않아 저장 순서가 보장되지 않는다. 작업을 먼저 넣어야
    # 이 작업을 가리키는 기록(job_event, episode.job_id)이 외래 키에 걸리지 않는다
    s.flush()
    s.add(JobEvent(job_id=job.id, from_status=None, to_status="PENDING", actor="job-api", reason=None, at=now))
    return job


def _next_episode(s: Session, series: Series) -> Episode:
    if series.status == "PAUSED":
        raise ApiError(409, "series_paused", "앞 화가 반려돼 시리즈가 멈춰 있다. resume 후 다시 만든다")
    if series.status == "DONE":
        raise ApiError(409, "series_done", "시리즈의 모든 화를 만들었다")
    if series.status == "CANCELLED":
        raise ApiError(409, "series_cancelled", "취소된 시리즈다 (D29)")
    if series.status not in ("APPROVED", "ACTIVE"):
        raise ApiError(409, "series_not_approved", "승인되지 않은 시리즈 계획이다")
    ep = s.scalar(select(Episode).where(Episode.series_id == series.id, Episode.status == "PLANNED")
                  .order_by(Episode.number))
    if ep is None:
        raise ApiError(409, "series_no_planned_episode", "만들 화가 없다")
    if ep.number > 1:
        # D27: 앞 화가 승인 전이어도 다 만들어졌으면(REVIEW 이후) 다음 화를 미리 만든다. 승인·공개는 화 순서대로 (review.approve)
        # D31: 업로드만 남은 앞 화(한도 대기 등)도 다 만든 것으로 본다. 업로드 순서는 upload 단계가 지킨다
        prev = s.scalar(select(Episode).where(Episode.series_id == series.id, Episode.number == ep.number - 1))
        prev_job = s.get(Job, prev.job_id) if prev is not None and prev.job_id else None
        produced = prev_job is not None and (prev_job.status in PRODUCED or waiting_for_upload(prev_job))
        if prev is None or (prev.status not in EP_DONE and not produced):
            raise ApiError(409, "previous_episode_not_ready",
                           f"{ep.number - 1}화가 다 만들어진(qc 통과) 뒤에 {ep.number}화를 만든다 (D27·D31)")
    else:
        blocker = series_order.production_blocker(s, series)  # D33: 앞 시리즈를 다 만든 뒤에 다음 시리즈
        if blocker:
            raise ApiError(409, "previous_series_not_finished", blocker)
    return ep


def _create_episode_job(s: Session, settings, now: datetime, series: Series) -> Job:
    ep = _next_episode(s, series)
    job = _insert(s, settings, now, topic=ep.title, category=series.category, series_id=series.id,
                  episode_number=ep.number)
    ep.status = "IN_PRODUCTION"
    ep.job_id = job.id
    series.status = "ACTIVE"
    return job


def _check_auto_limits(s: Session, settings, now: datetime) -> None:
    today = s.scalar(select(func.count()).select_from(Job).where(Job.created_at >= kst_day_start_utc(now)))
    if today >= settings.daily_job_limit:
        raise ApiError(409, "daily_limit_reached", f"오늘 만든 작업이 한도({settings.daily_job_limit})에 닿았다")
    # 검토 대기 + 업로드 대기(D31): 미리 만든 영상이 끝없이 쌓이지 않게
    backlog = s.scalar(select(func.count()).select_from(Job).where(
        (Job.status == "REVIEW") | (Job.status.in_(("PENDING", "RUNNING", "WAITING")) & (Job.current_step == "upload"))))
    if backlog >= settings.review_backlog_limit:
        raise ApiError(409, "review_backlog_full",
                       f"검토·업로드 대기가 {backlog}건이라 새 작업을 만들지 않는다 (D15·D31)")


def create_job(s: Session, settings, now: datetime, *, topic: Optional[str], category: str,
               series_id: Optional[str]) -> Job:
    if series_id:
        series = s.get(Series, series_id)
        if series is None:
            raise ApiError(404, "series_not_found", f"시리즈가 없다: {series_id}")
        return _create_episode_job(s, settings, now, series)
    if topic:
        ensure_category(settings, category)
        return _insert(s, settings, now, topic=topic, category=category)
    return _auto_select(s, settings, now)


def create_news_job(s: Session, settings, now: datetime, *, title: str, news: dict) -> Job:
    """IT 뉴스 (D40): 텔레그램에서 고른 GeekNews 글. 단독 작업, 원문 정보는 작업 입력에 둔다(주제 단계가 원문을 읽는다)"""
    ensure_category(settings, "it-news")
    return _insert(s, settings, now, topic=title, category="it-news", extra={"news": news})


LISTICLE = "listicle"


def create_listicle_job(s: Session, settings, now: datetime, *, topic: str, count: int,
                        references: Optional[list[str]] = None, items: Optional[list[str]] = None) -> Job:
    """목록형 쇼츠 (D42): 텔레그램 /top·POST /listicle. 단독 작업, 참고 자료·항목 이름은 작업 입력에 두고 주제 단계가 읽는다"""
    ensure_category(settings, LISTICLE)
    items = [i.strip() for i in (items or []) if i.strip()]
    return _insert(s, settings, now, topic=topic, category=LISTICLE,
                   extra={"listicle": {"count": len(items) or count, "references": list(references or []), "items": items}})


def _auto_select(s: Session, settings, now: datetime) -> Job:
    _check_auto_limits(s, settings, now)
    skipped = []  # 왜 못 만들었는지 (no_candidates 알림에 싣는다. 2026-10-18: 이유가 숨어 원인을 찾기 어려웠다)
    for series in s.scalars(select(Series).where(Series.status.in_(("APPROVED", "ACTIVE")))
                            .order_by(Series.approved_at, Series.created_at)):
        try:
            return _create_episode_job(s, settings, now, series)
        except ApiError as e:
            if e.code != "series_no_planned_episode":
                skipped.append(f"- {series_order.label(s, series)}: {e.message}")
            continue  # 앞 화 승인 대기 등. 다음 후보로
    for t in s.scalars(select(Topic).where(Topic.status == "READY").order_by(Topic.created_at, Topic.id)):
        try:
            job = _insert(s, settings, now, topic=t.title, category=t.category, topic_id=t.id)
        except ApiError:
            continue
        t.status = "USED"
        return job
    raise ApiError(409, "no_candidates", "만들 수 있는 시리즈 화나 승인된 주제가 없다" + ("\n" + "\n".join(skipped) if skipped else ""))
