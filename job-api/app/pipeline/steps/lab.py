"""lab 단계: 실습 리뷰 실험 (실습리뷰쇼츠 아키텍처, 메인 D46). 다른 형식은 바로 지나간다.

1. 사람이 계획을 승인하기 전이면 '기다림(blocked)' 으로 멈춘다(텔레그램 [실험 시작]이 풀어 준다).
2. 과제 폴더(lab/<과제>/task.json)를 만들고 맥 위 실험 실행기를 부른다. 실행기는 과제마다 일회용 컨테이너를 띄운다.
3. 컨테이너가 남긴 result.json 을 읽어 evidence.json(대본·장면·검토의 유일한 근거)을 만든다.
   토큰 모양 문자열이 하나라도 남아 있으면 영상으로 가지 않게 멈춘다(2차 검사).
"""
from __future__ import annotations

import json
import re
import shutil
import time
from typing import Any, Callable, Optional

import httpx

from .base import StepContext, StepFailure

TOKEN_SHAPE = re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}")
POLL_SEC = 5
GRACE_SEC = 180


class LabStep:
    name = "lab"
    inputs = ["job.json"]
    outputs = ["lab.json", "evidence.json"]

    def __init__(self, http: Optional[httpx.Client] = None, sleep: Callable[[float], None] = time.sleep):
        self._http = http
        self._sleep = sleep

    def run(self, ctx: StepContext) -> None:
        job = ctx.read_json("job.json")
        if job.get("format") != "review":
            ctx.write_json("lab.json", {"skipped": True})
            ctx.write_json("evidence.json", {"skipped": True})
            return
        rv_input = (ctx.job.get("input") or {}).get("review") or {}
        if not rv_input.get("planApproved"):
            raise StepFailure("blocked", "실험 계획 승인 대기 (텔레그램 [실험 시작])")
        st = ctx.settings
        if not st.lab_runner_url or not st.lab_image:
            raise StepFailure("deterministic", "실험 실행기 설정(MINIBATCH_LAB_RUNNER_URL·MINIBATCH_LAB_IMAGE)이 없다")
        try:
            token = st.lab_runner_token_file.read_text(encoding="utf-8").strip()
        except OSError:
            raise StepFailure("deterministic", "실험 실행기 토큰 파일이 없다") from None
        tasks = job["review"]["tasks"]
        lab = ctx.job_dir / "lab"
        if lab.exists():
            shutil.rmtree(lab)  # 다시 하는 실험은 새 폴더에서 (지난 기록은 reset 이 attempt-N 으로 옮긴다)
        for t in tasks:
            d = lab / t["id"]
            d.mkdir(parents=True)
            d.chmod(0o777)  # 컨테이너는 1000:1000 으로 쓴다
            (d / "task.json").write_text(json.dumps({"prompt": t["prompt"], "timeoutSec": t["timeoutSec"], "maxTurns": 15,
                                                     "check": t.get("check") or {}}, ensure_ascii=False), encoding="utf-8")
        headers = {"Authorization": f"Bearer {token}"}
        http = self._http or httpx.Client(timeout=30)
        body = {"jobId": ctx.job_id, "image": st.lab_image, "tasks": [{"id": t["id"], "timeoutSec": t["timeoutSec"]} for t in tasks]}
        try:
            res = http.post(f"{st.lab_runner_url}/runs", json=body, headers=headers)
        except httpx.HTTPError as e:
            raise StepFailure("transient", f"실험 실행기에 닿지 않는다: {type(e).__name__}") from None
        if res.status_code == 409:
            raise StepFailure("transient", "실험 실행기가 다른 실험 중이다")
        if res.status_code != 202:
            raise StepFailure("deterministic", f"실험 실행기 거절 {res.status_code}: {res.text[:200]}")
        deadline = time.monotonic() + sum(t["timeoutSec"] + 60 for t in tasks) + GRACE_SEC
        run: dict[str, Any] = {}
        while time.monotonic() < deadline:
            self._sleep(POLL_SEC)
            try:
                r = http.get(f"{st.lab_runner_url}/runs/{ctx.job_id}", headers=headers)
            except httpx.HTTPError:
                continue
            if r.status_code == 200:
                run = r.json()
                if run.get("status") in ("done", "error"):
                    break
        else:
            raise StepFailure("transient", "실험이 시간 안에 끝나지 않았다(실행기 응답)")
        evidence = build_evidence(ctx, tasks, run)
        ctx.write_json("lab.json", {"runner": run, "ok": sum(1 for t in evidence["tasks"] if t["ok"]), "total": len(tasks)})
        ctx.write_json("evidence.json", evidence)
        if not any(t["ok"] for t in evidence["tasks"]):
            summary = "; ".join(f"{t['id']} {t['status']}: {t['check'].get('detail', '')}" for t in evidence["tasks"])
            raise StepFailure("deterministic", f"실험 과제가 모두 실패해 영상을 만들지 않는다: {summary}"[:600])


def build_evidence(ctx: StepContext, tasks: list[dict[str, Any]], run: dict[str, Any]) -> dict[str, Any]:
    by_id = {t.get("id"): t for t in run.get("tasks") or []}
    out = []
    for t in tasks:
        p = ctx.job_dir / "lab" / t["id"] / "result.json"
        raw = p.read_text(encoding="utf-8") if p.exists() else ""
        if TOKEN_SHAPE.search(raw):
            raise StepFailure("deterministic", f"{t['id']} 실험 기록에 토큰 모양 문자열이 남아 있어 멈춘다(보안)")
        r = json.loads(raw) if raw else {}
        rs = by_id.get(t["id"]) or {}
        status = r.get("status") or ("timeout" if rs.get("status") == "killed" else "no_result")
        out.append({
            "id": t["id"], "goal": t["goal"], "prompt": t["prompt"], "ok": bool(r.get("ok")), "status": status,
            "seconds": r.get("seconds", rs.get("seconds", 0)), "check": r.get("check") or {"ok": False, "detail": "결과 없음"},
            "steps": [{"kind": s.get("kind"), "input": str(s.get("input", ""))[:80], "output": [str(x)[:80] for x in s.get("output") or []][:3]}
                      for s in (r.get("steps") or [])[:8]],
            "files": (r.get("files") or [])[:8], "final": str(r.get("final") or "")[:400],
            "previews": [{"path": v["path"], "preview": f"lab/{t['id']}/{v['preview']}"} for v in r.get("previews") or []
                         if (ctx.job_dir / "lab" / t["id"] / v["preview"]).exists()][:2],
            "excerpts": (r.get("excerpts") or [])[:2],
        })
    return {"tool": "claude", "tasks": out}
