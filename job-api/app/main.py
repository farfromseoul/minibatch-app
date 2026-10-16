"""job-api: 단계 API (아키텍처 절충안 C, D2·D21). n8n 이 단계 순서를 지휘하고, 여기서는 단계 하나씩 실행한다.

uvicorn 은 작업자(worker) 하나로 띄운다. 전역 잠금(D4)이 프로세스 안의 잠금이기 때문이다.
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from typing import Callable, Optional

import httpx
from fastapi import FastAPI

from app.core import errors
from app.core.auth import load_token
from app.core.config import Settings
from app.core.timeutil import utcnow
from app.db.migrate import upgrade
from app.db.session import make_engine, make_sessionmaker
from app.pipeline.pipeline import PIPELINE
from app.pipeline.runner import Runner
from app.pipeline.steps import default_steps

from .api.routes import api, public

log = logging.getLogger("job-api")


def thread_executor(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="step", daemon=True).start()


def http_notify(url: str, payload: dict) -> None:
    """n8n Wait 노드의 재개 주소를 부른다 (아키텍처 흐름 1)."""
    httpx.post(url, json=payload, timeout=10).raise_for_status()


def create_app(settings: Optional[Settings] = None, *, steps: Optional[dict] = None,
               pipeline: Optional[list[str]] = None, executor: Callable = thread_executor,
               notify: Callable = http_notify, clock: Callable = utcnow) -> FastAPI:
    """테스트는 가짜 단계·즉시 실행기·가짜 시계를 넣는다. 실제 서버는 환경 변수로 정한다."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        s = settings or Settings.from_env()
        app.state.settings = s
        app.state.token = load_token(s.token_file)  # 없으면 시작하지 않는다
        s.data_dir.mkdir(parents=True, exist_ok=True)
        s.jobs_dir.mkdir(parents=True, exist_ok=True)
        engine = make_engine(s.db_path)
        upgrade(f"sqlite:///{s.db_path}")  # DB 구조를 최신으로 올린다
        app.state.db = make_sessionmaker(engine)
        app.state.clock = clock
        app.state.runner = Runner(settings=s, db=app.state.db, pipeline=pipeline or PIPELINE,
                                  steps={**default_steps(), **(steps or {})},  # 넘겨준 단계가 기본을 덮는다
                                  executor=executor, notify=notify, clock=clock)
        recovered = app.state.runner.recover()  # 규칙 8
        if recovered:
            log.warning("재시작 복구: 실행 중으로 남은 시도 %d건을 일시적 실패로 기록", recovered)
        yield
        app.state.runner.wait_idle(30)
        engine.dispose()

    app = FastAPI(title="minibatch job-api", lifespan=lifespan)
    errors.install(app)
    app.include_router(public)
    app.include_router(api)
    return app


app = create_app()
