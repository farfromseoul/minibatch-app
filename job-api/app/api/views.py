"""DB 행을 API 응답(JSON)으로 바꾼다. 필드 이름은 n8n 이 읽기 쉽게 camelCase."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import iso
from app.db.models import Artifact, Episode, Job, JobEvent, Publication, Series, StepRun, Topic


def job_summary(job: Job) -> dict[str, Any]:
    return {"id": job.id, "topic": job.topic, "topicKey": job.topic_key, "category": job.category,
            "status": job.status, "currentStep": job.current_step, "seriesId": job.series_id,
            "episodeNumber": job.episode_number, "errorSummary": job.error_summary,
            "createdAt": iso(job.created_at), "updatedAt": iso(job.updated_at)}


def job_detail(s: Session, job: Job) -> dict[str, Any]:
    runs = s.scalars(select(StepRun).where(StepRun.job_id == job.id, StepRun.superseded.is_(False))
                     .order_by(StepRun.started_at, StepRun.id)).all()
    arts = s.scalars(select(Artifact).where(Artifact.job_id == job.id, Artifact.superseded.is_(False))).all()
    events = s.scalars(select(JobEvent).where(JobEvent.job_id == job.id).order_by(JobEvent.id)).all()
    pub = s.get(Publication, job.id)
    return {
        **job_summary(job),
        "steps": [{"step": r.step, "attempt": r.attempt, "status": r.status, "kind": r.kind,
                   "retryFrom": r.retry_from, "error": r.error} for r in runs],
        "artifacts": [{"step": a.step, "kind": a.kind, "path": a.path, "sha256": a.sha256} for a in arts],
        "events": [{"from": e.from_status, "to": e.to_status, "actor": e.actor, "reason": e.reason,
                    "at": iso(e.at)} for e in events],
        "publication": None if pub is None else {
            "platform": pub.platform, "videoId": pub.video_id, "visibility": pub.visibility,
            "publishAt": iso(pub.publish_at), "approvedBy": pub.approved_by, "approvedAt": iso(pub.approved_at),
            "containsSyntheticMedia": pub.contains_synthetic_media,
            "url": f"https://www.youtube.com/shorts/{pub.video_id}" if pub.video_id else None},
    }


def series_detail(s: Session, series: Series) -> dict[str, Any]:
    eps = s.scalars(select(Episode).where(Episode.series_id == series.id).order_by(Episode.number)).all()
    return {"id": series.id, "category": series.category, "title": series.title, "bible": series.bible,
            "planSource": series.plan_source, "status": series.status, "approvedAt": iso(series.approved_at),
            "playlistId": series.youtube_playlist_id,
            "episodes": [{"number": e.number, "title": e.title, "outline": e.outline, "summary": e.summary,
                          "nextTeaser": e.next_teaser, "status": e.status, "jobId": e.job_id} for e in eps]}


def series_summary(s: Session, series: Series) -> dict[str, Any]:
    statuses = list(s.scalars(select(Episode.status).where(Episode.series_id == series.id)))
    return {"id": series.id, "category": series.category, "title": series.title, "status": series.status,
            "planSource": series.plan_source, "playlistId": series.youtube_playlist_id,
            "createdAt": iso(series.created_at), "approvedAt": iso(series.approved_at),
            "counts": {"total": len(statuses), "planned": statuses.count("PLANNED"),
                       "inProduction": statuses.count("IN_PRODUCTION"), "approved": statuses.count("APPROVED"),
                       "rejected": statuses.count("REJECTED")}}


def topic_view(t: Topic) -> dict[str, Any]:
    return {"id": t.id, "title": t.title, "category": t.category, "source": t.source, "status": t.status,
            "createdAt": iso(t.created_at)}
