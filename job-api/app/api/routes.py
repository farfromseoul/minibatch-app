"""job-api HTTP 경로 (아키텍처 "인터페이스 - job-api"). /healthz 말고는 모두 내부 토큰이 필요하다."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text

from app.core.auth import require_token
from app.core.errors import ApiError
from app.db.models import Job, Series, Topic
from app.domain import cancel as cancel_domain, generation, overview, review, series as series_domain, topics as topic_domain
from app.domain.jobs import create_job, create_listicle_job
from app.domain.upload_order import next_job
from app.publish import approve as publishing
from app.youtube.client import YouTubeError

from .views import job_detail, job_summary, series_detail, series_summary, topic_view

public = APIRouter()
api = APIRouter(dependencies=[Depends(require_token)])


def _st(request: Request):
    return request.app.state


def _llm(request: Request, step: str):
    providers = _st(request).providers
    if providers is None:
        raise ApiError(503, "llm_unavailable", "LLM 제공자 설정(providers.yaml)이 없다")
    return providers.llm(step)


# ---------- 요청 본문


class CreateJobBody(BaseModel):
    topic: Optional[str] = Field(default=None, min_length=1, max_length=200)
    category: str = "ai-it"
    seriesId: Optional[str] = None


class ListicleBody(BaseModel):
    """목록형 쇼츠 (D42). items 를 주면 그 개수가 count"""
    topic: str = Field(min_length=1, max_length=100)
    count: int = Field(default=5, ge=3, le=5)
    references: list[str] = Field(default_factory=list, max_length=5)
    items: list[str] = Field(default_factory=list, max_length=5)
    theme: Optional[str] = Field(default=None, max_length=30)  # 화면 테마 (v1.3). 없으면 추천


class StepBody(BaseModel):
    resumeUrl: Optional[str] = None


class ApproveBody(BaseModel):
    approvedBy: str = Field(min_length=1, max_length=100)
    publishAt: Optional[datetime] = None


class RejectBody(BaseModel):
    rejectedBy: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=2000)


class CancelBody(BaseModel):
    cancelledBy: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=2000)


class EpisodePlan(BaseModel):
    number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    outline: str = Field(min_length=1)


class SeriesBody(BaseModel):
    key: Optional[str] = None  # 계획 생성(episodeCount)이면 없어도 된다: s<날짜>-<순번>
    category: str = "ai-it"
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)  # 계획 생성이면 없어도 된다: LLM 이 정함
    bible: dict[str, Any] = Field(default_factory=dict)
    episodes: Optional[list[EpisodePlan]] = None
    episodeCount: Optional[int] = Field(default=None, ge=1, le=50)
    theme: Optional[str] = Field(default=None, min_length=1, max_length=100)  # 계획 생성: 사용자가 정한 주제 (D37)

    @field_validator("episodes")
    @classmethod
    def numbered_from_one(cls, v):
        if v is not None and [e.number for e in v] != list(range(1, len(v) + 1)):
            raise ValueError("화 번호는 1부터 빠짐없이 차례대로")
        return v


class ApproveSeriesBody(BaseModel):
    approvedBy: str = Field(min_length=1, max_length=100)
    episodes: Optional[list[EpisodePlan]] = None
    bible: Optional[dict[str, Any]] = None

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
    # 작업자가 죽어도 job-api 는 살아 있다. 상태는 ok 로 두고 경고만 단다 (n8n 이 5분마다 보고 알린다)
    for name, label, url in _worker_urls(st):
        checks[name] = _reachable(url)
        if not checks[name]:
            warnings.append(f"{label} 응답 없음: {url}")
    codex_warning = _codex_failures(st)
    if codex_warning:
        warnings.append(codex_warning)
    checks["youtube_token"], token_warning = _youtube_token(st)
    if token_warning:
        warnings.append(token_warning)
    status = "ok" if checks["db"] else "error"
    return JSONResponse(status_code=200 if checks["db"] else 503,
                        content={"status": status, "checks": checks, "warnings": warnings})


def _worker_urls(st) -> list[tuple[str, str, str]]:
    urls = []
    registry = st.providers
    if registry is not None:
        cfg = getattr(registry, "config", None) or {}
        llm = cfg.get("llm") or {}
        name = (llm.get("steps") or {}).get("script")
        base = ((llm.get("providers") or {}).get(name) or {}).get("base_url")
        if base:
            urls.append(("llm", "LLM 서버", base.rstrip("/") + "/models"))
        urls.append(("tts", "tts-worker", registry.tts_settings()["url"].rstrip("/") + "/healthz"))
    urls.append(("render", "render-worker", st.settings.render_worker_url.rstrip("/") + "/healthz"))
    return urls


CODEX_WARN_AFTER = 3


def _codex_failures(st) -> Optional[str]:
    """Codex 중계기가 알려 주는 연속 실패 (2026-10-26: 이틀 넘게 모든 요청이 10분 시간 초과 → 로컬 LLM 이었는데 경고가 없었다).
    대본 단계 제공자의 주소 뿌리에서 /healthz 를 읽는다. LM Studio 처럼 이 값을 주지 않는 서버면 넘어간다"""
    registry = st.providers
    cfg = getattr(registry, "config", None) or {} if registry is not None else {}
    llm = cfg.get("llm") or {}
    base = ((llm.get("providers") or {}).get((llm.get("steps") or {}).get("script")) or {}).get("base_url")
    if not base:
        return None
    root = base.rstrip("/").removesuffix("/v1")
    try:
        h = httpx.get(root + "/healthz", timeout=2.0).json()
    except (httpx.HTTPError, ValueError):
        return None
    n = h.get("consecutiveFailures") if isinstance(h, dict) else None
    if not isinstance(n, int) or n < CODEX_WARN_AFTER:
        return None
    return (f"Codex {n}번 연속 실패 → 로컬 LLM 으로 대신 처리 중 (마지막 성공 {h.get('lastSuccessAt') or '?'}, "
            f"마지막 오류: {str(h.get('lastError') or '')[:120]}). 맥미니에서 codex --version 이 응답하는지 본다 (운영 명령 5)")


def _reachable(url: str) -> bool:
    try:
        return httpx.get(url, timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


def _youtube_token(st) -> tuple[bool, Optional[str]]:
    """토큰 값은 읽기만 하고 내보내지 않는다. 동의 화면이 테스트 상태면 7일 뒤 만료라 6일째부터 알린다 (R20)"""
    path = st.settings.youtube_token_file
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, "YouTube 갱신 토큰 파일이 없다: 실행계획 15번으로 발급한다"
    if not data.get("refresh_token"):
        return False, "YouTube 갱신 토큰이 비어 있다: 실행계획 15번 ②~④로 다시 발급한다"
    created = data.get("created_at")
    if created:
        try:
            age = st.clock() - datetime.fromisoformat(created.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return True, None
        if age.days >= 6:
            return True, (f"YouTube 갱신 토큰 발급 {age.days}일 지남. 동의 화면이 테스트 상태면 7일에 만료된다: "
                          f"실행계획 15번 ②~④로 다시 발급한다")
    return True, None


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


@api.post("/listicle", status_code=201)
def post_listicle(body: ListicleBody, request: Request) -> dict[str, Any]:
    if any(not r.startswith(("http://", "https://")) for r in body.references):
        raise ApiError(400, "invalid_reference", "참고 자료는 http(s) 주소만")
    if body.items and not 3 <= len(body.items) <= 5:
        raise ApiError(400, "invalid_items", "항목 이름은 3~5개")
    st = _st(request)
    theme = None
    if body.theme:
        from app.core.category import load_category
        from app.domain import themes
        theme = themes.resolve(load_category(st.settings, "listicle"), body.theme)
        if theme is None:
            raise ApiError(400, "unknown_theme", f"없는 테마: {body.theme}")
    with st.db() as s:
        job, _ = create_listicle_job(s, st.settings, st.clock(), topic=body.topic, count=body.count,
                                     references=body.references, items=[i[:60] for i in body.items], theme=theme)
        s.commit()
        return job_summary(job)


@api.get("/jobs")
def list_jobs(request: Request, status: Optional[str] = Query(default=None)) -> dict[str, Any]:
    with _st(request).db() as s:
        q = select(Job).order_by(Job.created_at, Job.id)
        if status:
            q = q.where(Job.status == status)
        return {"items": [job_summary(j) for j in s.scalars(q)]}


@api.post("/produce/run")
def produce_run(request: Request) -> dict[str, Any]:
    """지금 생산: n8n 1번 웹훅을 부른다(텔레그램 /run 과 같다). 이미 돌고 있으면 started=false (2026-10-31)"""
    return _st(request).production.run()


@api.get("/jobs/next")
def get_next_job(request: Request) -> dict[str, Any]:
    _st(request).production.touch()  # 1번 워크플로가 다녀감 (/run 겹침 막기)
    """이어 할 작업 (D31). /jobs/{job_id} 보다 먼저 선언해야 'next' 가 작업 ID 로 잡히지 않는다"""
    st = _st(request)
    with st.db() as s:
        return next_job(s, st.clock())


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
    _st(request).production.touch()  # 1번 워크플로가 다녀감 (/run 겹침 막기)
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
    _st(request).production.touch()  # 1번 워크플로가 다녀감 (/run 겹침 막기)
    return _st(request).runner.reset(job_id, from_)


# ---------- 검토


@api.post("/jobs/{job_id}/approve")
def approve(job_id: str, body: ApproveBody, request: Request) -> dict[str, Any]:
    """승인을 기록하고 바로 공개 전환한다. YouTube 가 실패해도 승인은 남고(APPROVED), POST /publish 로 다시 한다"""
    st = _st(request)
    with st.db() as s:
        job = _get_job(s, job_id)
        result = publishing.approve_and_publish(s, st.settings, job, st.clock(), body.approvedBy, body.publishAt,
                                                st.youtube_factory)
        return {**job_summary(job), "publish": result}


@api.post("/jobs/{job_id}/publish")
def publish(job_id: str, request: Request) -> dict[str, Any]:
    """승인 뒤 공개 전환이 실패했을 때 다시 한다. YouTube 오류는 502 와 youtube_<종류>"""
    st = _st(request)
    with st.db() as s:
        job = _get_job(s, job_id)
        try:
            result = publishing.publish(s, st.settings, job, st.youtube_factory, st.clock())
        except YouTubeError as e:
            s.rollback()
            raise ApiError(502, f"youtube_{e.kind}", e.message) from e
        s.commit()
        return {**job_summary(job), "publish": result}


@api.post("/jobs/{job_id}/reject")
def reject(job_id: str, body: RejectBody, request: Request) -> dict[str, Any]:
    st = _st(request)
    with st.db() as s:
        job = _get_job(s, job_id)
        review.reject(s, job, st.clock(), body.rejectedBy, body.reason)
        s.commit()
        return job_summary(job)


@api.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, body: CancelBody, request: Request) -> dict[str, Any]:
    """공개 전 작업 취소 (D29). 시리즈 화면 시리즈를 멈춘다"""
    st = _st(request)
    with st.db() as s:
        job = _get_job(s, job_id)
        cancel_domain.cancel_job(s, job, st.clock(), body.cancelledBy, body.reason)
        s.commit()
        return job_summary(job)


# ---------- 시리즈 (D24)


@api.post("/series", status_code=201)
def post_series(body: SeriesBody, request: Request) -> dict[str, Any]:
    st = _st(request)
    if body.episodes is None:  # 화 수만(제목·key 는 있어도 없어도) → LLM 이 계획을 짜서 PROPOSED (D25, D27)
        if not body.episodeCount:
            raise ApiError(422, "invalid_request", "episodes 나 episodeCount 중 하나가 필요하다")
        llm = _llm(request, "series_plan")
        with st.runner.exclusive("시리즈 계획 생성"), st.db() as s:
            key = body.key or generation.next_series_key(s, st.clock())
            series = generation.generate_series_plan(s, st.settings, st.clock(), llm, key=key, category=body.category,
                                                     title=body.title, count=body.episodeCount, bible=body.bible or None,
                                                     theme=body.theme)
            s.commit()
            detail = series_detail(s, series)
        if st.telegram is not None:  # [계획 승인] 버튼 (D28)
            st.telegram.notify_plan(detail["id"])
        return detail
    if not body.key or not body.title:
        raise ApiError(422, "invalid_request", "화별 계획을 직접 줄 때는 key 와 title 이 필요하다")
    with st.db() as s:
        series = series_domain.create_user_series(
            s, st.settings, st.clock(), key=body.key, category=body.category, title=body.title,
            bible=body.bible, episodes=[e.model_dump() for e in body.episodes])
        s.commit()
        return series_detail(s, series)


class SeriesRequestBody(BaseModel):
    category: str = "ai-it"
    episodeCount: int = Field(default=10, ge=3, le=20)  # 자동으로 정하기를 누를 때의 화 수


@api.post("/series/request")
def request_series(body: SeriesRequestBody, request: Request) -> dict[str, Any]:
    """다음 시리즈 계획 전에 텔레그램으로 주제·화 수를 묻는다 (D37). 계획은 답이 오면 만든다"""
    st = _st(request)
    if st.telegram is None:
        raise ApiError(503, "telegram_off", "텔레그램이 꺼져 있어 주제를 물을 수 없다. POST /series 로 직접 만든다")
    return st.telegram.ask_series(body.category, body.episodeCount)


# ---------- 현황 (2026-10-20)


@api.get("/overview")
def get_overview(request: Request) -> dict[str, Any]:
    """시리즈 화별 상태(만듦·업로드 대기·검토·공개), 다음 계획(보냄·승인), 주제 질문, ASMR 을 한 번에. text 는 사람이 읽는 요약"""
    st = _st(request)
    return overview.collect(st.db, st.clock, telegram=st.telegram, asmr=st.asmr, news=getattr(st, "news", None))


# ---------- IT 뉴스 (D40)


@api.post("/news/daily")
def news_daily(request: Request) -> dict[str, Any]:
    """n8n 7번이 매일 07:00 부른다: GeekNews 새 글을 모아 평가하고 텔레그램으로 후보를 보낸다"""
    return _st(request).news.daily()


@api.get("/news/items")
def news_items(request: Request, status: Optional[str] = Query(default=None)) -> dict[str, Any]:
    from app.db.models import NewsItem
    with _st(request).db() as s:
        q = select(NewsItem).order_by(NewsItem.created_at.desc(), NewsItem.id.desc()).limit(100)
        if status:
            q = q.where(NewsItem.status == status)
        return {"items": [{"id": x.id, "title": x.title, "status": x.status, "score": x.score, "points": x.points,
                           "readable": x.readable, "copyrightRisk": x.copyright_risk, "sourceUrl": x.source_url,
                           "gnUrl": x.gn_url, "jobId": x.job_id} for x in s.scalars(q)]}


@api.post("/news/items/{item_id}/pick")
def news_pick(item_id: str, request: Request) -> dict[str, Any]:
    st = _st(request)
    return {"message": st.news.pick(item_id)}


# ---------- ASMR 채널 (D38)


class AsmrActionBody(BaseModel):
    by: str = Field(default="운영자", min_length=1, max_length=100)


@api.post("/asmr/scan")
def asmr_scan(request: Request) -> dict[str, Any]:
    """n8n 이 1시간마다 부른다: inbox 의 새 영상에 업로드 승인을 묻고, 승인된 영상을 올린다"""
    return _st(request).asmr.scan()


@api.get("/asmr/videos")
def asmr_list(request: Request, status: Optional[str] = Query(default=None)) -> dict[str, Any]:
    return {"items": _st(request).asmr.list(status)}


@api.get("/asmr/videos/{vid}")
def asmr_get(vid: str, request: Request) -> dict[str, Any]:
    return _st(request).asmr.get(vid)


@api.post("/asmr/videos/{vid}/{action}")
def asmr_action(vid: str, action: str, body: AsmrActionBody, request: Request) -> dict[str, Any]:
    """텔레그램 버튼과 같은 일: approve-upload, publish, reject"""
    asmr = _st(request).asmr
    acts = {"approve-upload": asmr.approve_upload, "publish": asmr.publish, "reject": asmr.reject}
    if action not in acts:
        raise ApiError(404, "unknown_action", f"없는 동작: {action}")
    message = acts[action](vid, body.by)
    if action == "approve-upload":
        asmr.process_queue()
    return {"message": message, **asmr.get(vid)}


def _get_series(s, series_id: str) -> Series:
    series = s.get(Series, series_id)
    if series is None:
        raise ApiError(404, "series_not_found", f"시리즈가 없다: {series_id}")
    return series


@api.get("/series")
def list_series(request: Request, status: Optional[str] = Query(default=None)) -> dict[str, Any]:
    """시리즈와 화 상태별 개수. n8n 이 남은 화가 부족한지 보고 다음 계획을 만든다 (D27)"""
    with _st(request).db() as s:
        q = select(Series).order_by(Series.created_at, Series.id)
        if status:
            q = q.where(Series.status == status)
        return {"items": [series_summary(s, x) for x in s.scalars(q)]}


@api.get("/series/{series_id}")
def get_series(series_id: str, request: Request) -> dict[str, Any]:
    with _st(request).db() as s:
        return series_detail(s, _get_series(s, series_id))


@api.post("/series/{series_id}/approve")
def approve_series(series_id: str, body: ApproveSeriesBody, request: Request) -> dict[str, Any]:
    st = _st(request)
    with st.db() as s:
        series = _get_series(s, series_id)
        generation.approve_series_plan(s, series, st.clock(),
                                       [e.model_dump() for e in body.episodes] if body.episodes is not None else None,
                                       body.bible)
        s.commit()
        return series_detail(s, series)


@api.post("/series/{series_id}/cancel")
def cancel_series(series_id: str, body: CancelBody, request: Request) -> dict[str, Any]:
    """시리즈 취소 (D29). 공개 전 화·작업도 취소, 공개된 화는 그대로"""
    st = _st(request)
    with st.db() as s:
        series = _get_series(s, series_id)
        cancel_domain.cancel_series(s, series, st.clock(), body.cancelledBy, body.reason)
        s.commit()
        return series_detail(s, series)


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


@api.post("/topics/generate", status_code=201)
def generate_topics(body: GenerateBody, request: Request) -> dict[str, Any]:
    st = _st(request)
    llm = _llm(request, "topics")
    with st.runner.exclusive("주제 후보 생성"), st.db() as s:
        created = generation.generate_topics(s, st.settings, st.clock(), llm, body.category, body.count)
        s.commit()
        return {"created": len(created), "items": [topic_view(t) for t in created]}


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
