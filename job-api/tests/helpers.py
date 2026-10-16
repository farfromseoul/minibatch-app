"""테스트 공통 도구: 임시 데이터 폴더, 가짜 단계, 즉시 실행기, 재개 주소 기록기."""
from __future__ import annotations

import json
import pathlib
import tempfile
import threading
import unittest
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.pipeline.steps.base import StepFailure

TOKEN = "test-token-not-secret"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeStep:
    """입력 파일을 읽고 출력 파일 하나를 쓰는 단계. 실패·대기를 흉내 낼 수 있다."""

    def __init__(self, name, inputs, outputs, fail=None, block=None, partial_then_fail=False):
        self.name = name
        self.inputs = inputs
        self.outputs = outputs
        self.fail = fail  # StepFailure 또는 예외
        self.block = block  # threading.Event: set 될 때까지 기다린다
        self.partial_then_fail = partial_then_fail
        self.runs = 0

    def run(self, ctx):
        self.runs += 1
        if self.block is not None:
            self.block.wait(5)
        if self.partial_then_fail:
            ctx.write_text(self.outputs[0], "반쯤")
            raise RuntimeError("쓰다가 죽음")
        if self.fail is not None:
            raise self.fail
        for out in self.outputs:
            ctx.write_text(out, json.dumps({"step": self.name, "run": self.runs}))


def inline_executor(fn):
    """백그라운드 스레드 대신 그 자리에서 실행한다. API는 그래도 202를 돌려준다."""
    fn()


class Clock:
    def __init__(self, start=datetime(2026, 10, 16, 1, 0, 0)):  # UTC. 한국 시각 10:00
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


class AppTestCase(unittest.TestCase):
    pipeline = ["topic", "script", "review"]

    def make_steps(self):
        return {
            "script": FakeStep("script", ["job.json"], ["script.json"]),
            "review": FakeStep("review", ["script.json"], ["review.json"]),
        }

    def make_providers(self):
        return None  # LLM 단계 테스트는 가짜 레지스트리를 넣는다

    def extra_settings(self):
        return {}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self._tmp.name)
        token_file = root / "job_api_token"
        token_file.write_text(TOKEN + "\n")
        (root / "content" / "categories").mkdir(parents=True)
        (root / "content" / "categories" / "ai-it.yaml").write_text("key: ai-it\ntitle: AI·IT 개념 설명\n")
        self.settings = Settings(
            data_dir=root / "data",
            db_path=root / "data" / "db" / "minibatch.sqlite",
            token_file=token_file,
            content_dir=root / "content",
            daily_job_limit=3,
            review_backlog_limit=6,
            **self.extra_settings(),
        )
        self.clock = Clock()
        self.resumed = []
        self.steps = self.make_steps()
        self.app = create_app(
            self.settings,
            steps=self.steps,
            pipeline=self.pipeline,
            executor=inline_executor,
            notify=lambda url, payload: self.resumed.append((url, payload)),
            clock=self.clock,
            providers=self.make_providers(),
        )
        self.client = TestClient(self.app)
        self.client.__enter__()  # lifespan(DB 이전, 재시작 복구) 실행

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self._tmp.cleanup()

    # 편의 함수
    def post(self, path, body=None, **kw):
        return self.client.post(path, json=body or {}, headers=AUTH, **kw)

    def get(self, path, **kw):
        return self.client.get(path, headers=AUTH, **kw)

    def new_job(self, topic="RAG란?", **body):
        res = self.post("/jobs", {"topic": topic, **body})
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()["id"]

    def run_step(self, job_id, step, resume_url=None):
        body = {"resumeUrl": resume_url} if resume_url else {}
        return self.post(f"/jobs/{job_id}/steps/{step}", body)

    def run_until(self, job_id, last):
        for step in self.pipeline:
            res = self.run_step(job_id, step)
            self.assertIn(res.status_code, (200, 202), f"{step}: {res.text}")
            if step == last:
                return

    def job_dir(self, job_id):
        return self.settings.data_dir / "jobs" / job_id


__all__ = ["AppTestCase", "FakeStep", "StepFailure", "AUTH", "TOKEN", "threading"]
