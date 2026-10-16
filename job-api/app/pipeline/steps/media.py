"""tts · timeline · visuals · render 단계 (앱 설계 "TTS", "타임라인 계산", 아키텍처 D5·D18).

작업자(tts-worker, render-worker)와는 경로만 주고받는다. 두 작업자도 데이터 폴더를 같은 경로(/data)로 붙인다.
"""
from __future__ import annotations

import shutil
from typing import Any

import httpx

from app.core.category import load_category
from app.pipeline.timeline_calc import compute_timeline
from app.text.pronunciation import apply_pronunciation, load_dictionary

from .base import StepContext, StepFailure


def _post(url: str, body: dict, timeout: float, what: str, retry_from_on_422: str | None = None) -> dict:
    """작업자 호출. 연결 실패·시간 초과·409·5xx 는 transient, 400 은 deterministic, 422 는 retry_from 으로"""
    try:
        res = httpx.post(url, json=body, timeout=timeout)
    except httpx.TimeoutException as e:
        raise StepFailure("transient", f"{what} 시간 초과({timeout:.0f}초)") from e
    except httpx.HTTPError as e:
        raise StepFailure("transient", f"{what} 연결 실패: {type(e).__name__}") from e
    if res.status_code == 409 or res.status_code >= 500:
        raise StepFailure("transient", f"{what} {res.status_code}: {res.text[:300]}")
    if res.status_code == 422 and retry_from_on_422:
        raise StepFailure("deterministic", f"{what} 입력 검증 실패: {res.text[:500]}", retry_from=retry_from_on_422)
    if res.status_code >= 400:
        raise StepFailure("deterministic", f"{what} 요청 거절 {res.status_code}: {res.text[:300]}")
    return res.json()


class TtsStep:
    name = "tts"
    inputs = ["scenes.json"]
    outputs = ["tts", "tts.json"]

    def run(self, ctx: StepContext) -> None:
        scenes = ctx.read_json("scenes.json")
        job = ctx.read_json("job.json")
        cat = load_category(ctx.settings, job["category"])
        settings = ctx.providers.tts_settings()
        words = load_dictionary(ctx.settings.content_dir / "pronunciation.yaml", cat.get("pronunciation"))
        voice = (cat.get("voices") or {}).get(settings.get("engine")) or settings.get("voice")
        sentences = []
        for sc in scenes["scenes"]:
            for j, text in enumerate(sc["lines"], start=1):
                sentences.append({"id": f"{sc['id']}-{j:02d}", "scene": sc["id"], "text": text,
                                  "spoken": apply_pronunciation(text, words)})
        # 작업자가 임시 폴더에 쓰게 하고 다 끝나면 이름을 바꾼다 (반쯤 만든 tts/ 가 남지 않게, 규칙 5)
        tmp = ctx.job_dir / f"tts.tmp-{ctx.attempt}"
        final = ctx.job_dir / "tts"
        try:
            res = _post(settings["url"].rstrip("/") + "/synthesize",
                        {"out_dir": str(tmp), "voice": voice, "sentences": [{"id": s["id"], "text": s["spoken"]} for s in sentences]},
                        float(settings.get("timeout_sec", 900)), "tts-worker")
            if final.exists():
                shutil.rmtree(final)
            tmp.rename(final)
        finally:
            if tmp.exists():
                shutil.rmtree(tmp)
        seconds = {i["id"]: i["seconds"] for i in res["items"]}
        ctx.write_json("tts.json", {
            "engine": settings.get("engine"), "voice": voice, "sampleRate": res.get("sample_rate"),
            "items": [{**s, "path": f"tts/{s['id']}.wav", "seconds": seconds[s["id"]]} for s in sentences],
        })


class TimelineStep:
    name = "timeline"
    inputs = ["scenes.json", "tts.json"]
    outputs = ["timeline.json"]

    def run(self, ctx: StepContext) -> None:
        job = ctx.read_json("job.json")
        t = compute_timeline(ctx.read_json("scenes.json"), ctx.read_json("tts.json"), fps=job["fps"],
                             width=job["resolution"]["width"], height=job["resolution"]["height"], theme=job["theme"])
        seconds = t["durationInFrames"] / job["fps"]
        target = job["targetDurationSec"]
        if not target - 5 <= seconds <= target + 5:  # 55~65초 (기획서 성공 기준 1). 대본 길이로 맞춘다 (앱 설계 "길이 맞추기")
            raise StepFailure("deterministic", f"영상 길이 {seconds:.1f}초가 {target - 5}~{target + 5}초 밖이다", retry_from="script")
        ctx.write_json("timeline.json", t)


class VisualsStep:
    """생성 클립 장면만 처리한다 (D18). 시범 운영은 clip_engine none 이라 템플릿 그대로 통과한다"""

    name = "visuals"
    inputs = ["timeline.json"]
    outputs = ["visuals.json"]

    def run(self, ctx: StepContext) -> None:
        engine = getattr(ctx.providers, "clip_engine", "none") if ctx.providers else "none"
        t = ctx.read_json("timeline.json")
        if engine != "none" and any(s["visual"]["type"] == "clip" for s in t["scenes"]):
            raise StepFailure("deterministic", f"영상 생성기 {engine} 는 아직 구현되지 않았다 (Phase 2)")
        ctx.write_json("visuals.json", {"clipEngine": engine,
                                        "scenes": [{"id": s["id"], "source": s["visual"]["type"]} for s in t["scenes"]],
                                        "costUsd": 0})


class RenderStep:
    name = "render"
    inputs = ["timeline.json", "visuals.json", "tts"]
    outputs = ["render/final.mp4"]

    def run(self, ctx: StepContext) -> None:
        out = ctx.job_dir / "render" / "final.mp4"
        res: dict[str, Any] = _post(ctx.settings.render_worker_url.rstrip("/") + "/render",
                                    {"timeline": str(ctx.job_dir / "timeline.json"), "out": str(out)},
                                    float(ctx.settings.render_timeout_sec), "render-worker", retry_from_on_422="scenes")
        ctx.meta["render"] = res  # 렌더 시간·프레임 수는 step_run 기록용
