"""단계 하나를 실행하고 기록한다 (앱 설계 "runner 가 지키는 규칙" 1~8).

순서 지휘는 n8n 이 한다. 여기서는 한 번의 단계 요청이 규칙을 지키는지만 책임진다.
"""
from __future__ import annotations

import logging
import shutil
import threading
from datetime import datetime
from typing import Any, Callable, Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.timeutil import iso
from app.db.models import Artifact, Job, StepRun

from ..domain.status import RESETTABLE, RUNNABLE, set_status
from .files import inputs_hash, sha256_path
from .steps.base import Step, StepContext, StepFailure

log = logging.getLogger("job-api.runner")

TRANSIENT_LIMIT = 3  # 같은 단계의 일시적 실패가 이만큼 쌓이면 FAILED (앱 설계 "재시도와 실패 종류")


class Runner:
    def __init__(self, *, settings, db: Callable[[], Session], pipeline: list[str], steps: dict[str, Step],
                 executor: Callable[[Callable[[], None]], None], notify: Callable[[str, dict], None],
                 clock: Callable[[], datetime], providers: Any = None):
        self.settings = settings
        self.providers = providers
        self.db = db
        self.pipeline = pipeline
        self.steps = steps
        self.executor = executor
        self.notify = notify
        self.clock = clock
        self._lock = threading.Lock()  # 규칙 2: 한 번에 한 단계 (메모리 예산, D4)
        self._idle = threading.Event()
        self._idle.set()
        self._running_job: Optional[str] = None

    # ---------- 조회

    def _current_run(self, s: Session, job_id: str, step: str) -> Optional[StepRun]:
        return s.scalar(select(StepRun).where(StepRun.job_id == job_id, StepRun.step == step,
                                              StepRun.superseded.is_(False))
                        .order_by(StepRun.attempt.desc()))

    def step_status(self, job_id: str, step: str) -> dict[str, Any]:
        self._known_step(step)
        with self.db() as s:
            self._job(s, job_id)
            run = self._current_run(s, job_id, step)
            if run is None:
                return {"step": step, "status": "not_started", "attempt": 0, "kind": None,
                        "retryFrom": None, "retryAt": None, "error": None}
            return {"step": step, "status": run.status, "attempt": run.attempt, "kind": run.kind,
                    "retryFrom": run.retry_from, "retryAt": run.retry_at, "error": run.error,
                    "startedAt": iso(run.started_at), "finishedAt": iso(run.finished_at)}

    def wait_idle(self, timeout: float) -> bool:
        return self._idle.wait(timeout)

    def _known_step(self, step: str) -> None:
        if step not in self.pipeline:
            raise ApiError(404, "unknown_step", f"없는 단계: {step}")

    def _job(self, s: Session, job_id: str) -> Job:
        job = s.get(Job, job_id)
        if job is None:
            raise ApiError(404, "job_not_found", f"작업이 없다: {job_id}")
        return job

    # ---------- 실행 요청 (POST /jobs/{id}/steps/{step})

    def start(self, job_id: str, step_name: str, resume_url: Optional[str]) -> tuple[int, dict[str, Any]]:
        self._known_step(step_name)
        step = self.steps.get(step_name)
        if step is None:
            raise ApiError(501, "step_not_implemented", f"아직 구현되지 않은 단계: {step_name}")
        with self.db() as s:
            job = self._job(s, job_id)
            if job.status not in RUNNABLE:
                raise ApiError(409, "job_not_runnable", f"이 상태에서는 단계를 실행하지 않는다: {job.status}"
                                                        " (FAILED·REJECTED 는 reset 뒤에)")
            for prev in self.pipeline[: self.pipeline.index(step_name)]:  # 규칙 1: 순서 확인
                run = self._current_run(s, job_id, prev)
                if run is None or run.status != "succeeded":
                    raise ApiError(409, "previous_step_incomplete", f"앞 단계가 끝나지 않았다: {prev}")

        if not self._lock.acquire(blocking=False):  # 규칙 2
            raise ApiError(409, "busy", f"다른 단계가 실행 중이다: {self._running_job}")
        try:
            job_dir = self.settings.jobs_dir / job_id
            in_hash = inputs_hash(job_dir, step.inputs)
            with self.db() as s:
                job = self._job(s, job_id)
                done = self._already_done(s, job_id, step, in_hash)  # 규칙 3: 멱등
                if done is not None:
                    self._lock.release()
                    return 200, {"status": "already_done", "step": step_name, "attempt": done}
                attempt = (s.scalar(select(func.max(StepRun.attempt))
                                    .where(StepRun.job_id == job_id, StepRun.step == step_name)) or 0) + 1
                now = self.clock()
                s.add(StepRun(job_id=job_id, step=step_name, attempt=attempt, status="running",
                              input_hash=in_hash, superseded=False, started_at=now))
                set_status(s, job, "RUNNING", now)
                job.current_step = step_name
                job.updated_at = now
                ctx_job = {"id": job.id, "topic": job.topic, "topicKey": job.topic_key, "category": job.category,
                           "seriesId": job.series_id, "episodeNumber": job.episode_number}
                s.commit()
        except BaseException:
            if self._lock.locked():
                self._lock.release()
            raise

        self._running_job = job_id
        self._idle.clear()
        ctx = StepContext(job_id=job_id, step=step_name, attempt=attempt, job_dir=job_dir, job=ctx_job,
                          settings=self.settings, db=self.db, providers=self.providers)
        self.executor(lambda: self._execute(step, ctx, resume_url))  # 규칙 4: 비동기
        return 202, {"status": "started", "step": step_name, "attempt": attempt}

    def _already_done(self, s: Session, job_id: str, step: Step, in_hash: str) -> Optional[int]:
        run = self._current_run(s, job_id, step.name)
        if run is None or run.status != "succeeded" or run.input_hash != in_hash:
            return None
        arts = s.scalars(select(Artifact).where(Artifact.job_id == job_id, Artifact.step == step.name,
                                                Artifact.superseded.is_(False))).all()
        recorded = {a.path: a.sha256 for a in arts}
        job_dir = self.settings.jobs_dir / job_id
        for out in step.outputs:
            p = job_dir / out
            if out not in recorded or not p.exists() or sha256_path(p) != recorded[out]:
                return None
        return run.attempt

    # ---------- 실행 (백그라운드)

    def _execute(self, step: Step, ctx: StepContext, resume_url: Optional[str]) -> None:
        result: dict[str, Any]
        try:
            try:
                ctx.job_dir.mkdir(parents=True, exist_ok=True)
                step.run(ctx)
                missing = [o for o in step.outputs if not (ctx.job_dir / o).exists()]
                if missing:
                    raise StepFailure("deterministic", f"단계가 출력을 만들지 않았다: {missing}", retry_from=step.name)
                result = self._record_success(step, ctx)
            except StepFailure as f:
                self._cleanup(ctx)
                result = self._record_failure(ctx, f.kind, f.message, f.retry_from, f.retry_at)
            except Exception as e:  # 모르는 예외는 일시적 실패로 본다
                log.exception("단계 실패 %s %s", ctx.job_id, ctx.step)
                self._cleanup(ctx)
                result = self._record_failure(ctx, "transient", f"{type(e).__name__}: {e}", None, None)
        except Exception:  # 기록 자체가 실패해도 잠금은 푼다
            log.exception("단계 결과 기록 실패 %s %s", ctx.job_id, ctx.step)
            result = {"jobId": ctx.job_id, "step": ctx.step, "attempt": ctx.attempt, "status": "failed",
                      "kind": "transient", "error": "결과 기록 실패"}
        finally:
            self._running_job = None
            self._lock.release()
            self._idle.set()
        if resume_url:
            try:
                self.notify(resume_url, result)
            except Exception:  # 재개 주소가 실패해도 결과는 GET 으로 조회할 수 있다
                log.warning("재개 주소 호출 실패 %s %s", ctx.job_id, ctx.step)

    def _cleanup(self, ctx: StepContext) -> None:
        """실패한 시도가 이번에 쓴 파일과 임시 파일을 지운다. 반쯤 쓴 결과가 남지 않게 (규칙 5)."""
        for p in ctx.written:
            if p.is_file():
                p.unlink()
        for tmp in ctx.job_dir.glob(f"**/*.tmp-{ctx.attempt}"):
            tmp.unlink()

    def _record_success(self, step: Step, ctx: StepContext) -> dict[str, Any]:  # 규칙 6
        now = self.clock()
        with self.db() as s:
            s.execute(update(Artifact).where(Artifact.job_id == ctx.job_id, Artifact.step == step.name,
                                             Artifact.superseded.is_(False)).values(superseded=True))
            for out in step.outputs:
                p = ctx.job_dir / out
                s.add(Artifact(job_id=ctx.job_id, step=step.name, kind="dir" if p.is_dir() else "file",
                               path=out, sha256=sha256_path(p), superseded=False))
            run = self._attempt(s, ctx)
            run.status = "succeeded"
            run.finished_at = now
            if ctx.degraded_notes:
                run.kind = "degraded"
                run.error = "; ".join(ctx.degraded_notes)
            job = s.get(Job, ctx.job_id)
            if step.name == self.pipeline[-1]:
                set_status(s, job, "REVIEW", now)
            s.commit()
        return {"jobId": ctx.job_id, "step": ctx.step, "attempt": ctx.attempt, "status": "succeeded",
                "kind": "degraded" if ctx.degraded_notes else None}

    def _record_failure(self, ctx: StepContext, kind: str, message: str, retry_from: Optional[str],
                        retry_at: Optional[str]) -> dict[str, Any]:
        now = self.clock()
        with self.db() as s:
            run = self._attempt(s, ctx)
            run.status, run.kind, run.error = "failed", kind, message[:2000]
            run.retry_from, run.retry_at, run.finished_at = retry_from, retry_at, now
            job = s.get(Job, ctx.job_id)
            if kind == "deterministic":
                set_status(s, job, "FAILED", now, reason=message[:500])
            elif kind == "quota":
                set_status(s, job, "WAITING", now, reason=f"다시 할 시각 {retry_at}")
            else:
                s.flush()
                transient = s.scalar(select(func.count()).select_from(StepRun).where(
                    StepRun.job_id == ctx.job_id, StepRun.step == ctx.step, StepRun.superseded.is_(False),
                    StepRun.status == "failed", StepRun.kind == "transient"))
                if transient >= TRANSIENT_LIMIT:
                    set_status(s, job, "FAILED", now, reason=f"일시적 실패 {transient}번: {message[:300]}")
            job.error_summary = message[:500]
            s.commit()
        return {"jobId": ctx.job_id, "step": ctx.step, "attempt": ctx.attempt, "status": "failed",
                "kind": kind, "retryFrom": retry_from, "retryAt": retry_at, "error": message[:500]}

    def _attempt(self, s: Session, ctx: StepContext) -> StepRun:
        return s.scalar(select(StepRun).where(StepRun.job_id == ctx.job_id, StepRun.step == ctx.step,
                                              StepRun.attempt == ctx.attempt))

    # ---------- 되돌리기 (규칙 7)

    def reset(self, job_id: str, from_step: str) -> dict[str, Any]:
        if from_step not in self.pipeline:
            raise ApiError(400, "unknown_step", f"없는 단계: {from_step}")
        if self._running_job == job_id:
            raise ApiError(409, "busy", "이 작업의 단계가 실행 중이다")
        steps_after = self.pipeline[self.pipeline.index(from_step):]
        with self.db() as s:
            job = self._job(s, job_id)
            if job.status not in RESETTABLE:
                raise ApiError(409, "job_not_resettable", f"이 상태에서는 되돌리지 않는다: {job.status}")
            job_dir = self.settings.jobs_dir / job_id
            n = len([p for p in job_dir.glob("attempt-*") if p.is_dir()]) + 1 if job_dir.exists() else 1
            target = job_dir / f"attempt-{n}"
            moved = []
            for name in steps_after:
                step = self.steps.get(name)
                for out in (step.outputs if step else []):
                    src = job_dir / out
                    if src.exists():
                        dst = target / out
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(src), str(dst))
                        moved.append(out)
            s.execute(update(StepRun).where(StepRun.job_id == job_id, StepRun.step.in_(steps_after))
                      .values(superseded=True))
            s.execute(update(Artifact).where(Artifact.job_id == job_id, Artifact.step.in_(steps_after))
                      .values(superseded=True))
            now = self.clock()
            set_status(s, job, "RUNNING", now, reason=f"reset from={from_step}")
            idx = self.pipeline.index(from_step)
            job.current_step = self.pipeline[idx - 1] if idx > 0 else None
            s.commit()
        return {"status": "reset", "from": from_step, "attemptDir": f"attempt-{n}" if moved else None,
                "moved": moved}

    # ---------- 재시작 복구 (규칙 8)

    def recover(self) -> int:
        now = self.clock()
        with self.db() as s:
            runs = s.scalars(select(StepRun).where(StepRun.status == "running")).all()
            for run in runs:
                run.status, run.kind, run.finished_at = "failed", "transient", now
                run.error = "job-api 재시작으로 중단됨"
            s.commit()
            return len(runs)
