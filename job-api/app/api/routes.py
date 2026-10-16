"""job-api HTTP 경로 (아키텍처 "인터페이스 - job-api"). /healthz 말고는 모두 내부 토큰이 필요하다."""
from __future__ import annotations

import shutil
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text

from app.core.auth import require_token
from app.core.errors import ApiError
from app.db.models import Job, Series, Topic
from app.domain import review, series as series_domain, topics as topic_domain
from app.domain.jobs import create_job

from .views import job_detail, job_summary, series_detail, topic_view

public = APIRouter()
api = APIRouter(dependencies=[Depends(require_token)])


def _st(request: Request):
    return request.app.state


# ---------- 요청 본문


class CreateJobBody(BaseModel):
    topic: Optional[str] = Field(default=None, min_length=1, max_length=200)
    category: str = "ai-it"
    seriesId: Optional[str] = None


class StepBody(BaseModel):
    resumeUrl: Optional[str] = None


class ApproveBody(BaseModel):
    approvedBy: str = Field(min_length=1, max_length=100)
    publishAt: Optional[datetime] = None


class RejectBody(BaseModel):
    rejectedBy: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=2000)


class EpisodePlan(BaseModel):
    number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    outline: str = Field(min_length=1)


class SeriesBody(BaseModel):
    key: Optional[str] = None
    category: str = "ai-it"
    title: str = Field(min_length=1, max_length=200)
    bible: dict[str, Any] = Field(default_factory=dict)
    episodes: Optional[list[EpisodePlan]] = None
    episodeCount: Optional[int] = Field(default=None, ge=1, le=50)

    @field_validator("episodes")
    @classmethod
    def numbered_from_one(cls, v):
        if v is not None and [e.number for e in v] != list(range(1, len(v) + 1)):
            raise ValueError("화 번호는 1부터 빠짐없이 차례대로")
        return v


class TopicsBody(BaseModel):
    category: str = "ai-it"
    titles: list[str] = Field(min_length=1, max_length=200)


class GenerateBody(BaseModel):
    category: str = "ai-it"
    count: int = Field(default=10, ge=1, le=50)


# ---------- 상태 확인 (토큰 없음)


@public.get("/healthz")
def healthz(request: Request) -> dict[str, Any]:
    st = _st(request)
    checks: dict[str, Any] = {}
    warnings = []
    try:
        with st.db() as s:
            s.execute(text("SELECT 1"))
        checks["db"] = True
    except Exception:
        checks["db"] = False
        warnings.append("DB 연결 실패")
    free_gb = shutil.disk_usage(st.settings.data_dir).free / 1e9
    checks["disk_free_gb"] = round(free_gb, 1)
    if free_gb < st.settings.disk_free_warn_gb:
        warnings.append(f"디스크 여유 {free_gb:.0f}GB < {st.settings.disk_free_warn_gb}GB")
    # LLM 서버·tts-worker·render-worker 연결 확인은 작업 순서 20-d 에서 더한다
    status = "ok" if checks["db"] else "error"
    return JSONResponse(status_code=200 if checks["db"] else 503,
                        content={"status": status, "checks": checks, "warnings": warnings})


# ---------- 단계 순서


@api.get("/pipeline")
def pipeline(request: Request) -> dict[str, Any]:
    return {"steps": _st(request).runner.pipeline}


# ---------- 작업


@api.post("/jobs", status_code=201)
def post_job(body: CreateJobBody, request: Request) -> dict[str, Any]:
    st = _st(request)
    with st.db() as s:
        job = create_job(s, st.settings, st.clock(), topic=body.topic, category=body.category,
                         series_id=body.seriesId)
        s.commit()
        return job_summary(job)


@api.get("/jobs")
def list_jobs(request: Request, status: Optional[str] = Query(default=None)) -> dict[str, Any]:
    with _st(request).db() as s:
        q = select(Job).order_by(Job.created_at, Job.id)
        if status:
            q = q.where(Job.status == status)
        return {"items": [job_summary(j) for j in s.scalars(q)]}


def _get_job(s, job_id: str) -> Job:
    job = s.get(Job, job_id)
    if job is None:
        raise ApiError(404, "job_not_found", f"작업이 없다: {job_id}")
    return job


@api.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict[str, Any]:
    with _st(request).db() as s:
        return job_detail(s, _get_job(s, job_id))


# ---------- 단계 실행


@api.post("/jobs/{job_id}/steps/{step}")
def post_step(job_id: str, step: str, body: StepBody, request: Request):
    st = _st(request)
    if body.resumeUrl and not body.resumeUrl.startswith(st.settings.resume_url_prefix):
        raise ApiError(422, "invalid_request", f"resumeUrl 은 {st.settings.resume_url_prefix} 로 시작해야 한다")
    code, payload = st.runner.start(job_id, step, body.resumeUrl)
    return JSONResponse(status_code=code, content=payload)


@api.get("/jobs/{job_id}/steps/{step}")
def get_step(job_id: str, step: str, request: Request) -> dict[str, Any]:
    return _st(request).runner.step_status(job_id, step)


@api.post("/jobs/{job_id}/reset")
def reset(job_id: str, request: Request, from_: str = Query(alias="from")) -> dict[str, Any]:
    return _st(request).runner.reset(job_id, from_)


# ---------- 검토


@api.post("/jobs/{job_id}/approve")
def approve(job_id: str, body: ApproveBody, request: Request) -> dict[str, Any]:
    st = _st(request)
    with st.db() as s:
        job = _get_job(s, job_id)
        review.approve(s, st.settings, job, st.clock(), body.approvedBy, body.publishAt)
        s.commit()
        return job_summary(job)


@api.post("/jobs/{job_id}/reject")
def reject(job_id: str, body: RejectBody, request: Request) -> dict[str, Any]:
    st = _st(request)
    with st.db() as s:
        job = _get_job(s, job_id)
        review.reject(s, job, st.clock(), body.rejectedBy, body.reason)
        s.commit()
        return job_summary(job)


# ---------- 시리즈 (D24)


@api.post("/series", status_code=201)
def post_series(body: SeriesBody, request: Request) -> dict[str, Any]:
    st = _st(request)
    if body.episodes is None:
        raise ApiError(501, "not_implemented", "화별 계획 자동 생성은 작업 순서 20-d 에서 구현한다")
    if not body.key:
        raise ApiError(422, "invalid_request", "사용자가 쓴 시리즈는 key 가 필요하다")
    with st.db() as s:
        series = series_domain.create_user_series(
            s, st.settings, st.clock(), key=body.key, category=body.category, title=body.title,
            bible=body.bible, episodes=[e.model_dump() for e in body.episodes])
        s.commit()
        return series_detail(s, series)


def _get_series(s, series_id: str) -> Series:
    series = s.get(Series, series_id)
    if series is None:
        raise ApiError(404, "series_not_found", f"시리즈가 없다: {series_id}")
    return series


@api.get("/series/{series_id}")
def get_series(series_id: str, request: Request) -> dict[str, Any]:
    with _st(request).db() as s:
        return series_detail(s, _get_series(s, series_id))


@api.post("/series/{series_id}/resume")
def resume_series(series_id: str, request: Request) -> dict[str, Any]:
    with _st(request).db() as s:
        series = _get_series(s, series_id)
        series_domain.resume(s, series)
        s.commit()
        return series_detail(s, series)


# ---------- 주제 (D25)


@api.post("/topics", status_code=201)
def post_topics(body: TopicsBody, request: Request) -> dict[str, Any]:
    st = _st(request)
    with st.db() as s:
        created = topic_domain.add_user_topics(s, st.settings, st.clock(), body.category, body.titles)
        s.commit()
        return {"created": created}


@api.post("/topics/generate")
def generate_topics(body: GenerateBody) -> dict[str, Any]:
    raise ApiError(501, "not_implemented", "주제 자동 생성은 작업 순서 20-d 에서 구현한다")


@api.get("/topics")
def list_topics(request: Request, status: Optional[str] = Query(default=None)) -> dict[str, Any]:
    with _st(request).db() as s:
        q = select(Topic).order_by(Topic.created_at, Topic.id)
        if status:
            q = q.where(Topic.status == status)
        return {"items": [topic_view(t) for t in s.scalars(q)]}


def _decide_topic(topic_id: int, request: Request, approve_it: bool) -> dict[str, Any]:
    with _st(request).db() as s:
        topic = s.get(Topic, topic_id)
        if topic is None:
            raise ApiError(404, "topic_not_found", f"주제가 없다: {topic_id}")
        topic_domain.decide(topic, approve_it)
        s.commit()
        return topic_view(topic)


@api.post("/topics/{topic_id}/approve")
def approve_topic(topic_id: int, request: Request) -> dict[str, Any]:
    return _decide_topic(topic_id, request, True)


@api.post("/topics/{topic_id}/reject")
def reject_topic(topic_id: int, request: Request) -> dict[str, Any]:
    return _decide_topic(topic_id, request, False)
