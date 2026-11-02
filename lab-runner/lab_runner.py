"""실습 리뷰 실험 실행기 (실습리뷰쇼츠 아키텍처 H-D1·H-D6, 2026-11-01).

맥 위 LaunchAgent(127.0.0.1:1236). job-api 가 과제 폴더(<데이터>/jobs/<작업>/lab/<과제>/task.json)를 만든 뒤 부르면,
과제마다 일회용 실험 컨테이너를 띄우고 시간 상한이 지나면 끝낸다.

- 파일은 읽고 쓰지 않는다: LaunchAgent 는 외장 데이터 볼륨에 못 쓴다(08 문서). 경로만 도커에 넘긴다.
- 셸 명령을 받지 않는다: 받는 것은 작업·과제 이름과 이미지 이름뿐(형식 검사). 과제 내용은 task.json 에 있다.
- 컨테이너: root 아님, 읽기 전용, 권한 제거, 자원 상한, 실험망(바깥 길 없음) + 허용 목록 프록시, DNS 없음.
- job-api 와는 실행기 토큰(Bearer)으로 확인한다. 한 번에 한 작업.
- 공식 스킬(실습 리뷰 A, 2026-11-02): 계획에 적힌 스킬 폴더만 허용 저장소(기본 anthropics/skills)의 tarball 에서 꺼내
  캐시(홈 아래)에 두고 컨테이너에 읽기 전용으로 붙인다. 링크·장치 파일·폴더 밖 경로·크기 초과는 거절한다. 컨테이너는 여전히 인터넷 차단.
- 표준 라이브러리만 (맥 기본 python3 3.9).

실행: python3 lab_runner.py  (환경 변수는 Config.from_env)
"""
from __future__ import annotations

import hmac
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import threading
import time
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional

log = logging.getLogger("lab-runner")

JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
TASK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,19}$")
IMAGE = re.compile(r"^[A-Za-z0-9./_-]*minibatch-lab:[A-Za-z0-9._-]+$")
MAX_TASKS = 3
KEEP_RUNS = 20
MAX_SKILLS = 2
SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
SKILL_PATH = re.compile(r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$")


def github_fetch(url: str, timeout: Optional[float] = None):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "minibatch-lab-runner"}), timeout=timeout)


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
    skill_cache: str = os.path.expanduser("~/Library/Caches/minibatch-lab")
    skill_repos: tuple = ("anthropics/skills",)
    skill_max_bytes: int = 20 * 1024 * 1024
    skill_max_files: int = 500

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
                   job_timeout_sec=int(e.get("LAB_JOB_TIMEOUT_SEC", "1800")),
                   skill_cache=e.get("LAB_SKILL_CACHE", os.path.expanduser("~/Library/Caches/minibatch-lab")),
                   skill_repos=tuple(x.strip() for x in e.get("LAB_SKILL_REPOS", "anthropics/skills").split(",") if x.strip()))


def docker_args(cfg: Config, job_id: str, task_id: str, image: str, skills: Optional[list] = None) -> list[str]:
    """실험 컨테이너 하나의 docker run 인자 (실행계획 4단계와 같은 옵션). 받은 공식 스킬은 읽기 전용으로"""
    work = os.path.join(cfg.data_dir, "jobs", job_id, "lab", task_id)
    mounts = []
    for sk in skills or []:
        mounts += ["-v", f"{os.path.join(cfg.skill_cache, job_id, sk['name'])}:/work/workspace/.claude/skills/{sk['name']}:ro"]
    return [cfg.docker, "run", "--rm", "--name", container_name(job_id, task_id),
            "--network", cfg.network, "--dns", "127.0.0.1",
            "--user", cfg.user, "--read-only", "--tmpfs", "/tmp:rw,exec,size=512m", "--tmpfs", "/home/lab:rw,exec,size=256m",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "512",
            "--memory", cfg.memory, "--cpus", cfg.cpus,
            "-e", f"HTTPS_PROXY={cfg.proxy}", "-e", f"HTTP_PROXY={cfg.proxy}", "-e", "NO_PROXY=",
            "--env-file", cfg.env_file,
            "-v", f"{work}:/work", *mounts, image]


def container_name(job_id: str, task_id: str) -> str:
    return f"lab-{job_id}-{task_id}"[:120]


class Runner:
    def __init__(self, cfg: Config, run: Callable[..., Any] = subprocess.run, clock: Callable[[], float] = time.time,
                 fetch: Callable[..., Any] = github_fetch):
        self.cfg = cfg
        self._run = run
        self._fetch = fetch
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
        self.validate_skills(body)
        return job_id, image, out

    def validate_skills(self, body: Any) -> list[dict[str, str]]:
        skills = body.get("skills") or [] if isinstance(body, dict) else []
        if not isinstance(skills, list) or len(skills) > MAX_SKILLS:
            raise ValueError(f"skills 는 {MAX_SKILLS}개까지")
        out = []
        for sk in skills:
            if not isinstance(sk, dict):
                raise ValueError("스킬 형식이 틀렸다")
            name, repo, path = sk.get("name"), sk.get("repo"), sk.get("path")
            if not isinstance(name, str) or not SKILL_NAME.match(name):
                raise ValueError("스킬 이름 형식이 틀렸다")
            if repo not in self.cfg.skill_repos:
                raise ValueError(f"허용하지 않은 저장소: {repo} (허용: {', '.join(self.cfg.skill_repos)})")
            if not isinstance(path, str) or not SKILL_PATH.match(path) or ".." in path.split("/"):
                raise ValueError("스킬 경로 형식이 틀렸다")
            out.append({"name": name, "repo": repo, "path": path})
        if len({x["name"] for x in out}) != len(out):
            raise ValueError("스킬 이름이 겹친다")
        return out

    def fetch_skill(self, job_id: str, sk: dict[str, str]) -> dict[str, Any]:
        """저장소 tarball 에서 그 스킬 폴더만 꺼낸다. 링크·장치·폴더 밖·크기 초과는 거절"""
        dest = os.path.join(self.cfg.skill_cache, job_id, sk["name"])
        if os.path.exists(dest):
            shutil.rmtree(dest)
        with self._fetch(f"https://api.github.com/repos/{sk['repo']}/tarball", timeout=60) as res:
            data = res.read(self.cfg.skill_max_bytes * 4 + 1)
        if len(data) > self.cfg.skill_max_bytes * 4:
            raise ValueError("저장소 묶음이 너무 크다")
        files, total = 0, 0
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            for m in tf.getmembers():
                parts = m.name.split("/", 1)
                if len(parts) < 2 or not (parts[1] + "/").startswith(sk["path"] + "/"):
                    continue
                rel = parts[1][len(sk["path"]):].lstrip("/")
                if not rel or m.isdir():
                    continue
                if not m.isfile() or rel.startswith("/") or ".." in rel.split("/"):
                    raise ValueError(f"스킬 안에 허용하지 않는 항목: {rel or m.name}")
                files, total = files + 1, total + m.size
                if files > self.cfg.skill_max_files or total > self.cfg.skill_max_bytes:
                    raise ValueError("스킬이 너무 크다")
                target = os.path.join(dest, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with tf.extractfile(m) as src, open(target, "wb") as out:
                    out.write(src.read())
        if not os.path.isfile(os.path.join(dest, "SKILL.md")):
            raise ValueError(f"{sk['path']} 에 SKILL.md 가 없다")
        return {"name": sk["name"], "files": files}

    def start(self, body: Any, background: bool = True) -> dict[str, Any]:
        job_id, image, tasks = self.validate(body)
        skills = self.validate_skills(body)
        if not self._lock.acquire(blocking=False):
            raise BusyError(f"다른 실험이 실행 중이다: {self.current}")
        self.current = job_id
        rec = {"jobId": job_id, "status": "running", "startedAt": self._clock(),
               "tasks": [{"id": t["id"], "status": "pending"} for t in tasks]}
        self.runs[job_id] = rec
        while len(self.runs) > KEEP_RUNS:
            self.runs.pop(next(iter(self.runs)))
        if background:
            threading.Thread(target=self._work, args=(rec, image, tasks, skills), daemon=True).start()
        else:
            self._work(rec, image, tasks, skills)
        return {"jobId": job_id, "status": rec["status"]}

    def _work(self, rec: dict[str, Any], image: str, tasks: list[dict[str, Any]], skills: Optional[list] = None) -> None:
        job_id = rec["jobId"]
        deadline = self._clock() + self.cfg.job_timeout_sec
        try:
            try:
                rec["skills"] = [self.fetch_skill(job_id, sk) for sk in skills or []]
            except Exception as e:  # 스킬을 못 받으면 흉내 내지 않고 실험을 하지 않는다
                raise RuntimeError(f"스킬을 받지 못했다: {e}"[:300]) from None
            for t, out in zip(tasks, rec["tasks"]):
                left = deadline - self._clock()
                if left <= 10:
                    out.update(status="skipped", reason="작업 시간 상한")
                    continue
                limit = min(t["timeoutSec"] + 60, left)  # 컨테이너 안 스크립트가 먼저 끊고 결과를 쓰게 1분 여유
                out["status"] = "running"
                started = self._clock()
                try:
                    p = self._run(docker_args(self.cfg, job_id, t["id"], image, skills), capture_output=True, text=True, timeout=limit)
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
            rec["status"], rec["error"] = "error", (str(e) if isinstance(e, RuntimeError) else f"{type(e).__name__}: {e}")[:300]
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
