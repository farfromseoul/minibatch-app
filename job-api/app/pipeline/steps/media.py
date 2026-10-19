"""tts · timeline · visuals · render 단계 (앱 설계 "TTS", "타임라인 계산", 아키텍처 D5·D18).

작업자(tts-worker, render-worker)와는 경로만 주고받는다. 두 작업자도 데이터 폴더를 같은 경로(/data)로 붙인다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
import shutil
import subprocess
from typing import Any, Callable, Optional

import httpx

from app.core.category import load_category
from app.llm.prompting import render_messages
from app.media.ffmpeg import normalize_loudness
from app.stock.pixabay import Pixabay, StockError
from app.pipeline.timeline_calc import compute_timeline
from app.text.pronunciation import apply_pronunciation, load_dictionary

from .base import StepContext, StepFailure
from .llm_common import ask


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


QUERY_SCHEMA = {"type": "object", "properties": {"queries": {"type": "array", "items": {
    "type": "object", "properties": {"scene": {"type": "string"}, "query": {"type": "string"},
                                     "kind": {"type": "string", "enum": ["video", "image"]}},
    "required": ["scene", "query", "kind"], "additionalProperties": False}}}, "required": ["queries"], "additionalProperties": False}
RECENT_USED = 150     # 최근 이만큼 쓴 Pixabay 소재는 다시 고르지 않는다 (2026-10-19: 커버가 다 비슷하다는 피드백)
RECENT_QUERIES = 40   # 최근 검색어를 LLM 에 알려 겹치지 않게
HISTORY_KEEP = 500


class VisualsStep:
    """생성 클립(D18, Phase 2)과 스톡 영상(2026-10-17)을 처리한다.

    레터박스 스타일이고 providers.yaml 의 video.stock.engine 이 pixabay 면, LLM 이 장면마다 영어 검색어를 정하고
    Pixabay 에서 영상을 받아 clips/<장면>.mp4 로 둔다. 실패한 장면은 템플릿(도식)으로 두고 영상은 계속 만든다(degraded).
    """

    name = "visuals"
    inputs = ["timeline.json", "scenes.json"]
    outputs = ["visuals.json"]

    def __init__(self, stock_factory: Optional[Callable[..., Any]] = None):
        self._stock_factory = stock_factory or Pixabay.from_settings

    def run(self, ctx: StepContext) -> None:
        engine = getattr(ctx.providers, "clip_engine", "none") if ctx.providers else "none"
        t = ctx.read_json("timeline.json")
        if engine != "none" and any(s["visual"]["type"] == "clip" for s in t["scenes"]):
            raise StepFailure("deterministic", f"영상 생성기 {engine} 는 아직 구현되지 않았다 (Phase 2)")
        scenes = [{"id": s["id"], "source": s["visual"]["type"]} for s in t["scenes"]]
        stock_cfg = (getattr(ctx.providers, "stock", None) or {}) if ctx.providers else {}
        credits: list[dict[str, str]] = []
        if t.get("theme") == "letterbox" and stock_cfg.get("engine") == "pixabay":
            credits = self._stock(ctx, t, scenes, stock_cfg)
        ctx.write_json("visuals.json", {"clipEngine": engine, "stockEngine": stock_cfg.get("engine", "none"),
                                        "scenes": scenes, "credits": credits, "costUsd": 0})

    def _stock(self, ctx: StepContext, t: dict, scenes: list[dict], cfg: dict) -> list[dict[str, str]]:
        lines = {s["id"]: s for s in ctx.read_json("scenes.json")["scenes"]}
        listing = "\n".join(f"- {s['id']} ({lines.get(s['id'], {}).get('visual', {}).get('component', '')}): "
                             f"{' '.join(lines.get(s['id'], {}).get('lines', []))}" for s in t["scenes"])
        history_path = ctx.settings.data_dir / "cache" / "pixabay" / "used.json"
        history = _read_history(history_path)
        recent_ids = {(h.get("kind", "video"), h.get("id")) for h in history[-RECENT_USED:]}
        recent_queries = list(dict.fromkeys(h["query"] for h in reversed(history) if h.get("query")))[:RECENT_QUERIES]
        messages, _ = render_messages("visual_queries", scenes=listing, max_count=int(cfg.get("max_per_video", 6)),
                                      recent="\n".join(f"- {q}" for q in recent_queries) or "- (없음)")
        try:
            out = ask(ctx, messages, QUERY_SCHEMA, "visual_queries",
                      lambda d: [] if isinstance(d, dict) and isinstance(d.get("queries"), list) else ["queries 배열이 필요하다"])
            queries = {q["scene"]: (q["query"].strip(), q.get("kind") if q.get("kind") in ("video", "image") else "video")
                       for q in out.data.get("queries", []) if q.get("query", "").strip()}
        except StepFailure as e:
            ctx.note_degraded(f"스톡 검색어를 정하지 못해 도식으로: {e.message[:200]}")
            return []
        try:
            stock = self._stock_factory(ctx.settings, cfg)
        except StockError as e:
            ctx.note_degraded(f"스톡 공급원을 쓸 수 없어 도식으로: {e.message}")
            return []
        credits, used = [], 0
        picked: set = set()
        for scene, src in zip(t["scenes"], scenes):
            q, kind = queries.get(scene["id"], ("", "video"))
            if not q or used >= int(cfg.get("max_per_video", 6)):
                continue
            seconds = round(scene["durationInFrames"] / t["fps"], 2)
            clip = None
            try:
                # 고른 종류로 먼저, 쓸 만한 것이 없으면 다른 종류로. 최근 쓴 소재·이 영상에서 이미 쓴 소재는 건너뛴다
                for k in (kind, "image" if kind == "video" else "video"):
                    found = stock.search(q, seconds) if k == "video" else stock.search_images(q)
                    clip = next((c for c in found if (c.kind, c.id) not in recent_ids | picked), None)
                    if clip is not None:
                        break
                if clip is None:
                    ctx.note_degraded(f"{scene['id']} '{q}' 쓸 만한 새 소재 없음, 도식으로")
                    continue
                ext = "jpg" if clip.kind == "image" else "mp4"
                stock.download(clip, ctx.job_dir / "clips" / f"{scene['id']}.{ext}")
            except StockError as e:
                ctx.note_degraded(f"{scene['id']} 스톡 실패({e.kind}), 도식으로: {e.message}")
                continue
            used += 1
            picked.add((clip.kind, clip.id))
            history.append({"id": clip.id, "kind": clip.kind, "query": q, "job": ctx.job_id, "at": datetime.utcnow().strftime("%Y-%m-%d")})
            src.update({"source": "stock", "mediaType": clip.kind, "path": f"clips/{scene['id']}.{ext}", "durationSec": clip.duration,
                        "query": q, "credit": {"site": "Pixabay", "user": clip.user, "page": clip.page}})
            if all(c["user"] != clip.user for c in credits):
                credits.append({"site": "Pixabay", "user": clip.user, "page": clip.page})
        _write_history(history_path, history[-HISTORY_KEEP:])
        return credits


def _read_history(path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _write_history(path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


LOUDNESS_TARGET_LUFS = -14.0  # YouTube 가 큰 소리를 줄이는 기준으로 알려진 값 (공식 수치 미확인, 앱 설계 "품질 게이트")
TRUE_PEAK_DB = -1.5


class RenderStep:
    """render-worker 로 렌더한 뒤 job-api 에서 음량을 맞춘다 (작업 순서 20-d4).

    음량을 여기서 맞추는 이유: job-api 이미지에 ffmpeg 가 이미 있고, TTS 엔진을 바꾸거나 배경음악을 넣어도
    완성 영상 전체 기준으로 맞출 수 있다. 버린 대안: tts-worker 문장별 정규화(영상 전체 음량이 안 맞음),
    render-worker(Remotion 의 ffmpeg 호출 경로 확인과 이미지 재빌드 필요).
    """

    name = "render"
    inputs = ["timeline.json", "visuals.json", "tts", "clips"]
    outputs = ["render/final.mp4", "render.timeline.json"]

    def __init__(self, normalize: Optional[Callable[..., dict[str, Any]]] = None):
        self._normalize = normalize or normalize_loudness

    def run(self, ctx: StepContext) -> None:
        out = ctx.job_dir / "render" / "final.mp4"
        final = self._final_timeline(ctx)  # timeline 에 스톡 영상·위 제목을 더한 렌더 입력 (작업 폴더 맨 위: 상대 경로 기준)
        ctx.write_json("render.timeline.json", final)
        res = self._post_render(ctx, ctx.job_dir / "render.timeline.json", out)
        ctx.meta["render"] = res  # 렌더 시간·프레임 수는 step_run 기록용
        tmp = out.with_name(f"final.loudnorm-{ctx.attempt}.mp4")
        try:
            ctx.meta["loudnorm"] = self._normalize(out, tmp, target_i=LOUDNESS_TARGET_LUFS, true_peak=TRUE_PEAK_DB)
            os.replace(tmp, out)  # 다 쓴 뒤에 바꾼다 (규칙 5)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, OSError) as e:
            detail = getattr(e, "stderr", "") or str(e)
            raise StepFailure("deterministic", f"음량 맞추기 실패: {type(e).__name__} {str(detail)[-300:]}",
                              retry_from="render") from e
        finally:
            if tmp.exists():
                tmp.unlink()

    def _post_render(self, ctx: StepContext, timeline_path, out) -> dict[str, Any]:
        return _post(ctx.settings.render_worker_url.rstrip("/") + "/render", {"timeline": str(timeline_path), "out": str(out)},
                     float(ctx.settings.render_timeout_sec), "render-worker", retry_from_on_422="scenes")

    @staticmethod
    def _final_timeline(ctx: StepContext) -> dict[str, Any]:
        t = ctx.read_json("timeline.json")
        job = ctx.read_json("job.json")
        visuals = ctx.read_json("visuals.json") if ctx.path("visuals.json").is_file() else {"scenes": []}
        media = {s["id"]: s for s in visuals.get("scenes", []) if s.get("source") == "stock"}
        for scene in t["scenes"]:
            m = media.get(scene["id"])
            if m:
                if m.get("mediaType") == "image":  # 사진은 장면 내내 천천히 확대 (render 가 처리)
                    scene["media"] = {"type": "image", "src": m["path"]}
                else:
                    scene["media"] = {"type": "video", "src": m["path"], "durationInFrames": max(1, int(m["durationSec"] * t["fps"]))}
        cat = load_category(ctx.settings, job["category"])
        t["header"] = {"title": job["topic"]}
        if cat.get("brand"):  # 영상 위 브랜드 글자는 카테고리가 정할 때만 (기본 없음, 2026-10-18 사용자 피드백)
            t["header"]["brand"] = str(cat["brand"])
        return t
