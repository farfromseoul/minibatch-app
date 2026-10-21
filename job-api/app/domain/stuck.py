"""대본 검토에서 계속 떨어진 화 처리 (2026-10-21 사용자).

2026-10-21 실제: 4번째 시리즈 4화(키 합의)가 '구체성 2점'으로 세 번 떨어져 FAILED 로 멈췄고, 시리즈 전체가 멈췄다.
- 찾기(find_stuck): 점수 미달로 FAILED 인 시리즈 화 중, 마지막 '개요 고침' 뒤로 검토가 STUCK_AFTER 번 이상 떨어진 것
- 개요 고쳐 다시(revise_outline): LLM 이 검토 의견을 반영해 개요를 고친다. 그 뒤 주제 단계부터 되돌리면
  (topic 단계가 개요를 다시 읽는다) 생산 워크플로가 대본부터 다시 만들고 승인 요청까지 간다
- 건너뛰기(skip_episode): 작업은 취소, 화는 SKIPPED. 다음 화 만들기·승인·업로드 순서·시리즈 완료는 끝난 화로 본다(EP_DONE)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import Episode, Job, JobEvent, Series, StepRun
from app.llm.prompting import render_messages

from . import review
from .generation import _ask
from .status import set_status

# 대본 검토의 결정적 실패: 점수 미달과 치명 오류 둘 다 대본을 다시 써야 하는 실패라 같이 센다
# (2026-10-21 실제: 점수 미달만 세다가 '미달 2 + 치명 1' 인 6화에 질문을 보내지 않았다. decide.mjs 도 같은 기준)
REVIEW_FAILS = ("검토 점수 미달", "검토에서 치명 오류")
STUCK_AFTER = 3  # 생산 워크플로가 두 번 되돌려 세 번 써 본 뒤 (decide.mjs maxResets 2)
FIXED = "개요 고침"  # 이 이유의 작업 이력 뒤로 실패를 다시 센다 (decide.mjs 도 되돌리기 횟수를 여기서부터 센다)


def _episode(s: Session, job: Job) -> Optional[Episode]:
    return s.scalar(select(Episode).where(Episode.series_id == job.series_id, Episode.number == job.episode_number))


def _since_fix(s: Session, job: Job) -> Optional[datetime]:
    return s.scalar(select(JobEvent.at).where(JobEvent.job_id == job.id, JobEvent.reason.like(f"{FIXED}%"))
                    .order_by(JobEvent.at.desc()).limit(1))


def low_score_failures(s: Session, job: Job) -> list[str]:
    """마지막 개요 고침 뒤 대본 검토에서 떨어진 의견 (점수 미달·치명 오류, 되돌려서 지워진 시도도 센다)"""
    q = select(StepRun).where(StepRun.job_id == job.id, StepRun.step == "review", StepRun.status == "failed",
                              StepRun.kind == "deterministic", or_(*[StepRun.error.like(f"{p}%") for p in REVIEW_FAILS]))
    since = _since_fix(s, job)
    if since is not None:
        q = q.where(StepRun.started_at > since)
    return [r.error or "" for r in s.scalars(q.order_by(StepRun.started_at, StepRun.id))]


def find_stuck(s: Session) -> list[dict[str, Any]]:
    out = []
    for job in s.scalars(select(Job).where(Job.status == "FAILED", Job.series_id.is_not(None)).order_by(Job.created_at)):
        if job.current_step != "review":
            continue
        errors = low_score_failures(s, job)
        if len(errors) >= STUCK_AFTER:
            out.append({"job": job, "errors": errors})
    return out


def _stuck_job(s: Session, job_id: str) -> Job:
    job = s.get(Job, job_id)
    if job is None:
        raise ApiError(404, "job_not_found", f"작업이 없다: {job_id}")
    if job.status != "FAILED" or not job.series_id:
        raise ApiError(409, "not_stuck", f"검토에서 멈춘 시리즈 화가 아니다. 지금: {job.status}")
    return job


def revise_outline(s: Session, now: datetime, llm, job_id: str) -> str:
    job = _stuck_job(s, job_id)
    ep = _episode(s, job)
    series = s.get(Series, job.series_id)
    near = {e.number: e.title for e in s.scalars(select(Episode).where(
        Episode.series_id == job.series_id, Episode.number.in_([ep.number - 1, ep.number + 1])))}
    errors = low_score_failures(s, job) or [job.error_summary or ""]
    messages, _ = render_messages(
        "outline_fix", series_title=series.title, premise=(series.bible or {}).get("premise", ""), number=ep.number,
        title=ep.title, prev_title=near.get(ep.number - 1, "(첫 화)"), next_title=near.get(ep.number + 1, "(마지막 화)"),
        outline=ep.outline, feedback="\n".join(f"- {e}" for e in errors[-STUCK_AFTER:]))
    schema = {"type": "object", "properties": {"outline": {"type": "string"}}, "required": ["outline"], "additionalProperties": False}
    data = _ask(llm, messages, schema, "outline_fix",
                lambda d: [] if isinstance(d, dict) and len(str(d.get("outline") or "").strip()) >= 20 else ["outline 이 비었거나 너무 짧다"])
    new = str(data["outline"]).strip()
    old = ep.outline
    ep.outline = new
    s.add(JobEvent(job_id=job.id, from_status=job.status, to_status=job.status, actor="텔레그램", at=now,
                   reason=f"{FIXED}: 이전 개요: {old[:500]}"))
    return new


def skip_episode(s: Session, now: datetime, job_id: str, who: str) -> Episode:
    job = _stuck_job(s, job_id)
    ep = _episode(s, job)
    set_status(s, job, "CANCELLED", now, actor=who, reason=f"{ep.number}화 건너뛰기 (검토 {STUCK_AFTER}번 미달)")
    ep.status = "SKIPPED"
    review.finish_series_if_done(s, job.series_id)
    return ep
