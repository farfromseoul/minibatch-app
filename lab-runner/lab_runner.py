"""실습 리뷰 실험 실행기 (실습리뷰쇼츠 아키텍처 H-D1·H-D6, 2026-11-01).

맥 위 LaunchAgent(127.0.0.1:1236). job-api 가 과제 폴더(<데이터>/jobs/<작업>/lab/<과제>/task.json)를 만든 뒤 부르면,
과제마다 일회용 실험 컨테이너를 띄우고 시간 상한이 지나면 끝낸다.

- 파일은 읽고 쓰지 않는다: LaunchAgent 는 외장 데이터 볼륨에 못 쓴다(08 문서). 경로만 도커에 넘긴다.
- 셸 명령을 받지 않는다: 받는 것은 작업·과제 이름과 이미지 이름뿐(형식 검사). 과제 내용은 task.json 에 있다.
- 컨테이너: root 아님, 읽기 전용, 권한 제거, 자원 상한, 실험망(바깥 길 없음) + 허용 목록 프록시, DNS 없음.
- job-api 와는 실행기 토큰(Bearer)으로 확인한다. 한 번에 한 작업.
- 표준 라이브러리만 (맥 기본 python3 3.9).

실행: python3 lab_runner.py  (환경 변수는 Config.from_env)
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional

log = logging.getLogger("lab-runner")

JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
TASK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,19}$")
IMAGE = re.compile(r"^[A-Za-z0-9./_-]*minibatch-lab:[A-Za-z0-9._-]+$")
MAX_TASKS = 3
KEEP_RUNS = 20


@dataclass
class Config:
    data_dir: str
    env_file: str
    token: str
    network: str = "minibatch-lab"
    proxy: str = "http://172.31.250.2:3128"
    docker: str = "docker"
    task_timeout_sec: int = 600
    job_timeout_sec: int = 1800
    memory: str = "4g"
    cpus: str = "2"
    user: str = "1000:1000"

    @classmethod
    def from_env(cls, env=None) -> "Config":
        e = os.environ if env is None else env
        with open(e["LAB_TOKEN_FILE"], encoding="utf-8") as f:
            token = f.read().strip()
        if len(token) < 16:
            raise ValueError("실행기 토큰이 너무 짧다")
        return cls(data_dir=e["LAB_DATA_DIR"], env_file=e["LAB_ENV_FILE"], token=token,
                   network=e.get("LAB_NETWORK", "minibatch-lab"), proxy=e.get("LAB_PROXY", "http://172.31.250.2:3128"),
                   docker=e.get("LAB_DOCKER", "docker"),
                   task_timeout_sec=int(e.get("LAB_TASK_TIMEOUT_SEC", "600")),
                   job_timeout_sec=int(e.get("LAB_JOB_TIMEOUT_SEC", "1800")))


def docker_args(cfg: Config, job_id: str, task_id: str, image: str) -> list[str]:
    """실험 컨테이너 하나의 docker run 인자 (실행계획 4단계와 같은 옵션)"""
    work = os.path.join(cfg.data_dir, "jobs", job_id, "lab", task_id)
    return [cfg.docker, "run", "--rm", "--name", container_name(job_id, task_id),
            "--network", cfg.network, "--dns", "127.0.0.1",
            "--user", cfg.user, "--read-only", "--tmpfs", "/tmp:rw,exec,size=512m", "--tmpfs", "/home/lab:rw,exec,size=256m",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "512",
            "--memory", cfg.memory, "--cpus", cfg.cpus,
            "-e", f"HTTPS_PROXY={cfg.proxy}", "-e", f"HTTP_PROXY={cfg.proxy}", "-e", "NO_PROXY=",
            "--env-file", cfg.env_file,
            "-v", f"{work}:/work", image]


def container_name(job_id: str, task_id: str) -> str:
    return f"lab-{job_id}-{task_id}"[:120]


class Runner:
    def __init__(self, cfg: Config, run: Callable[..., Any] = subprocess.run, clock: Callable[[], float] = time.time):
        self.cfg = cfg
        self._run = run
        self._clock = clock
        self._lock = threading.Lock()
        self.runs: dict[str, dict[str, Any]] = {}
        self.current: Optional[str] = None

    def validate(self, body: Any) -> tuple[str, str, list[dict[str, Any]]]:
        if not isinstance(body, dict):
            raise ValueError("JSON 객체가 필요하다")
        job_id, image, tasks = body.get("jobId"), body.get("image"), body.get("tasks")
        if not isinstance(job_id, str) or not JOB_ID.match(job_id):
            raise ValueError("jobId 형식이 틀렸다")
        if not isinstance(image, str) or not IMAGE.match(image):
            raise ValueError("image 는 …minibatch-lab:<태그> 만")
        if not isinstance(tasks, list) or not 1 <= len(tasks) <= MAX_TASKS:
            raise ValueError(f"tasks 는 1~{MAX_TASKS}개")
        out = []
        for t in tasks:
            tid = t.get("id") if isinstance(t, dict) else None
            if not isinstance(tid, str) or not TASK_ID.match(tid):
                raise ValueError("과제 id 형식이 틀렸다")
            sec = t.get("timeoutSec", self.cfg.task_timeout_sec)
            if not isinstance(sec, int) or sec < 10:
                raise ValueError("timeoutSec 은 10 이상의 정수")
            out.append({"id": tid, "timeoutSec": min(sec, self.cfg.task_timeout_sec)})
        if len({t["id"] for t in out}) != len(out):
            raise ValueError("과제 id 가 겹친다")
        return job_id, image, out

    def start(self, body: Any, background: bool = True) -> dict[str, Any]:
        job_id, image, tasks = self.validate(body)
        if not self._lock.acquire(blocking=False):
            raise BusyError(f"다른 실험이 실행 중이다: {self.current}")
        self.current = job_id
        rec = {"jobId": job_id, "status": "running", "startedAt": self._clock(),
               "tasks": [{"id": t["id"], "status": "pending"} for t in tasks]}
        self.runs[job_id] = rec
        while len(self.runs) > KEEP_RUNS:
            self.runs.pop(next(iter(self.runs)))
        if background:
            threading.Thread(target=self._work, args=(rec, image, tasks), daemon=True).start()
        else:
            self._work(rec, image, tasks)
        return {"jobId": job_id, "status": rec["status"]}

    def _work(self, rec: dict[str, Any], image: str, tasks: list[dict[str, Any]]) -> None:
        job_id = rec["jobId"]
        deadline = self._clock() + self.cfg.job_timeout_sec
        try:
            for t, out in zip(tasks, rec["tasks"]):
                left = deadline - self._clock()
                if left <= 10:
                    out.update(status="skipped", reason="작업 시간 상한")
                    continue
                limit = min(t["timeoutSec"] + 60, left)  # 컨테이너 안 스크립트가 먼저 끊고 결과를 쓰게 1분 여유
                out["status"] = "running"
                started = self._clock()
                try:
                    p = self._run(docker_args(self.cfg, job_id, t["id"], image), capture_output=True, text=True, timeout=limit)
                    out.update(status="done" if p.returncode == 0 else "error", exitCode=p.returncode,
                               stderr=(p.stderr or "")[-400:])
                except subprocess.TimeoutExpired:
                    self._run([self.cfg.docker, "kill", container_name(job_id, t["id"])], capture_output=True, text=True, timeout=30)
                    out.update(status="killed", reason=f"{int(limit)}초 넘어 끝냄")
                out["seconds"] = round(self._clock() - started, 1)
                log.info("과제 %s/%s %s %.1f초", job_id, t["id"], out["status"], out["seconds"])
            rec["status"] = "done"
        except Exception as e:  # 실행기 오류는 작업 결과로 남기고 잠금은 푼다
            log.exception("실험 실패 %s", job_id)
            rec["status"], rec["error"] = "error", f"{type(e).__name__}: {e}"[:300]
        finally:
            rec["finishedAt"] = self._clock()
            self.current = None
            self._lock.release()

    def health(self) -> dict[str, Any]:
        try:
            p = self._run([self.cfg.docker, "network", "inspect", self.cfg.network, "--format", "{{.Internal}}"],
                          capture_output=True, text=True, timeout=15)
            docker = "ok" if p.returncode == 0 else "error"
            internal = (p.stdout or "").strip() == "true"
        except Exception:
            docker, internal = "error", False
        env_ok = os.path.isfile(self.cfg.env_file) and (os.stat(self.cfg.env_file).st_mode & 0o077) == 0
        return {"status": "ok" if docker == "ok" and internal and env_ok else "degraded", "docker": docker,
                "network": self.cfg.network, "networkInternal": internal, "envFile": "ok" if env_ok else "missing_or_open",
                "busy": self.current}


class BusyError(Exception):
    pass


def make_server(runner: Runner, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, obj: dict) -> None:
            data = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self) -> bool:
            got = self.headers.get("Authorization", "")
            return hmac.compare_digest(got.encode(), f"Bearer {runner.cfg.token}".encode())

        def do_GET(self):
            if self.path.rstrip("/") == "/healthz":
                return self._send(200, runner.health())
            if not self._authorized():
                return self._send(401, {"error": {"message": "실행기 토큰이 틀렸다"}})
            m = re.match(r"^/runs/([A-Za-z0-9_-]+)$", self.path)
            if m and m.group(1) in runner.runs:
                return self._send(200, runner.runs[m.group(1)])
            self._send(404, {"error": {"message": "없는 실험"}})

        def do_POST(self):
            if self.path.rstrip("/") != "/runs":
                return self._send(404, {"error": {"message": "없는 주소"}})
            if not self._authorized():
                return self._send(401, {"error": {"message": "실행기 토큰이 틀렸다"}})
            try:
                body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 65536)))
                self._send(202, runner.start(body))
            except BusyError as e:
                self._send(409, {"error": {"message": str(e)}})
            except ValueError as e:
                self._send(400, {"error": {"message": str(e)}})

        def log_message(self, fmt, *args):
            log.info("%s %s", self.address_string(), fmt % args)

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host, port = os.environ.get("LAB_HOST", "127.0.0.1"), int(os.environ.get("LAB_PORT", "1236"))
    cfg = Config.from_env()
    log.info("실험 실행기 %s:%d, 망=%s, 프록시=%s, 과제 상한 %d초", host, port, cfg.network, cfg.proxy, cfg.task_timeout_sec)
    make_server(Runner(cfg), host, port).serve_forever()


if __name__ == "__main__":
    main()
