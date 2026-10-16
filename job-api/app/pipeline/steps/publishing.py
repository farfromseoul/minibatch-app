"""qc · upload 단계 (앱 설계 "품질 게이트", "YouTube 게시", 아키텍처 D9·D26 ②).

qc 는 완성 영상을 ffprobe·ffmpeg 로 재고, 어긋나면 어느 단계부터 다시 할지(retry_from)를 알려 준다.
upload 는 비공개로 올리고, 시리즈 화면 시리즈 재생목록에 넣는다. 공개 전환은 승인 뒤 app/publish 가 한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from sqlalchemy import select

from app.core.category import load_category
from app.db.models import Episode, Job, Publication, Series
from app.media.ffmpeg import analyze as ffmpeg_analyze
from app.pipeline.files import sha256_path
from app.youtube.client import YouTube, YouTubeError

from .base import StepContext, StepFailure

SILENCE_FAIL_SEC = 2.5  # 장면 사이 무음은 1.6~1.85초가 정상이었다(2026-10-16 실제 영상 3편). 음성이 빠진 경우를 잡는다
LUFS_TARGET, LUFS_TOLERANCE = -14.0, 2.0  # 기준값 미확인이라 경고만 (앱 설계 "품질 게이트")
RETRY_ORDER = ["script", "scenes", "tts", "render"]  # 여러 검사가 어긋나면 가장 앞 단계부터 다시
DEFAULT_DISCLOSURE = "AI 도구로 대본과 음성을 만들었습니다"  # 카테고리에 없어도 비울 수 없다 (Supertonic 라이선스)


class QcStep:
    name = "qc"
    inputs = ["render/final.mp4", "timeline.json"]
    outputs = ["qc.json"]

    def __init__(self, analyze: Optional[Callable[..., dict[str, Any]]] = None):
        self._analyze = analyze or ffmpeg_analyze

    def run(self, ctx: StepContext) -> None:
        job = ctx.read_json("job.json")
        t = ctx.read_json("timeline.json")
        a = self._analyze(ctx.job_dir / "render" / "final.mp4", silence_db=-50, silence_min_sec=1.5)
        checks: list[dict[str, Any]] = []

        def check(name: str, ok: bool, value: Any, expected: str, retry_from: Optional[str] = None) -> None:
            checks.append({"name": name, "ok": bool(ok), "value": value, "expected": expected, "retryFrom": retry_from})

        target = job["targetDurationSec"]
        d = a["durationSec"]
        check("length", target - 5 <= d <= target + 5, round(d, 2), f"{target - 5}~{target + 5}초", "script")
        v = a.get("video") or {}
        check("resolution", (v.get("width"), v.get("height")) == (t["width"], t["height"]),
              f"{v.get('width')}x{v.get('height')}", f"{t['width']}x{t['height']}", "render")
        check("fps", abs(float(v.get("fps") or 0) - t["fps"]) < 0.01, v.get("fps"), str(t["fps"]), "render")
        check("frames", abs(int(v.get("frames") or 0) - t["durationInFrames"]) <= 1, v.get("frames"),
              f"{t['durationInFrames']}±1", "render")
        codecs = [s["codec"] for s in a.get("audio", [])]
        check("audio", codecs == ["aac"], codecs, "aac 1개", "render")
        longest = max((round(e - s, 2) for s, e in a.get("silences", [])), default=0.0)
        check("silence", longest <= SILENCE_FAIL_SEC, longest, f"{SILENCE_FAIL_SEC}초 이하", "tts")
        caps = t.get("captions", [])
        caps_ok = all(c["toFrame"] <= t["durationInFrames"] for c in caps) and \
            all(b["fromFrame"] >= p["toFrame"] for p, b in zip(caps, caps[1:]))
        check("captions", caps_ok, len(caps), "영상 안, 겹침 없음", "scenes")
        lufs = a.get("integratedLufs")
        loud_ok = lufs is not None and abs(lufs - LUFS_TARGET) <= LUFS_TOLERANCE
        check("loudness", loud_ok, lufs, f"{LUFS_TARGET}±{LUFS_TOLERANCE} LUFS (경고만)")
        warnings = [] if loud_ok else [f"음량 {lufs} LUFS 가 기준 {LUFS_TARGET}±{LUFS_TOLERANCE} 밖이다 (경고만)"]

        failed = [c for c in checks if not c["ok"] and c["retryFrom"]]
        if failed:
            retry = min((c["retryFrom"] for c in failed), key=RETRY_ORDER.index)
            names = {"length": "길이", "resolution": "해상도", "fps": "프레임률", "frames": "프레임 수",
                     "audio": "오디오", "silence": "무음", "captions": "자막"}
            detail = ", ".join(f"{names[c['name']]} {c['value']} (기준 {c['expected']})" for c in failed)
            raise StepFailure("deterministic", f"품질 검사 실패: {detail}", retry_from=retry)
        for w in warnings:
            ctx.note_degraded(w)
        ctx.write_json("qc.json", {"passed": True, "checks": checks, "warnings": warnings, "analysis": a})


def next_quota_reset(now: Optional[datetime] = None) -> str:
    """YouTube 할당량은 태평양 시각 자정에 다시 찬다. 그 5분 뒤 (UTC, ...Z)"""
    try:
        from zoneinfo import ZoneInfo
        tz: Any = ZoneInfo("America/Los_Angeles")
    except Exception:  # 시간대 자료가 없는 이미지: 겨울 시각(UTC-8)으로 잡으면 늦게 잡히지 일찍 잡히지는 않는다
        tz = timezone(timedelta(hours=-8))
    local = (now or datetime.now(timezone.utc)).astimezone(tz)
    nxt = (local + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return nxt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _description(script: dict[str, Any], playlist_id: Optional[str]) -> str:
    parts = [p for p in (script.get("hook"), script.get("summary")) if p]
    tags = " ".join(h if h.startswith("#") else f"#{h}" for h in script.get("hashtags", []))
    if tags:
        parts.append(tags)
    if playlist_id:
        parts.append(f"▶ 시리즈 전체 보기: https://www.youtube.com/playlist?list={playlist_id}")
    return "\n\n".join(parts)  # 고지 문구는 연결부(upload_video)가 끝에 붙인다


class UploadStep:
    name = "upload"
    inputs = ["render/final.mp4", "script.json", "visuals.json"]
    outputs = ["upload.json"]

    def __init__(self, youtube_factory: Optional[Callable[[Any], Any]] = None):
        self._factory = youtube_factory or YouTube.from_settings

    def run(self, ctx: StepContext) -> None:
        try:
            self._run(ctx)
        except YouTubeError as e:
            raise StepFailure(e.kind, e.message, retry_at=next_quota_reset() if e.kind == "quota" else None) from e

    def _run(self, ctx: StepContext) -> None:
        job = ctx.read_json("job.json")
        script = ctx.read_json("script.json")
        visuals = ctx.read_json("visuals.json")
        ycfg = load_category(ctx.settings, job["category"]).get("youtube") or {}
        disclosure = str(ycfg.get("disclosure") or DEFAULT_DISCLOSURE).strip()
        video = ctx.job_dir / "render" / "final.mp4"
        digest = sha256_path(video)
        synthetic = any(s.get("source") == "clip" for s in visuals.get("scenes", []))  # 생성 클립이 있으면 true (앱 설계 규칙 표)

        with ctx.db() as s:
            row = s.get(Job, ctx.job_id)
            pub = s.get(Publication, ctx.job_id)
            prev_video, prev_digest = (pub.video_id, pub.uploaded_sha256) if pub else (None, None)
            series = s.get(Series, row.series_id) if row.series_id else None
            info = None
            if series is not None:
                ep = s.scalar(select(Episode).where(Episode.series_id == series.id, Episode.number == row.episode_number))
                info = {"id": series.id, "title": series.title, "playlist": series.youtube_playlist_id,
                        "premise": str((series.bible or {}).get("premise", "")), "number": row.episode_number,
                        "episodeTitle": ep.title if ep else ""}

        yt = self._factory(ctx.settings)
        playlist_id = None
        if info is not None:
            playlist_id = info["playlist"]
            if not playlist_id:
                playlist_id = yt.create_playlist(info["title"], info["premise"])
                with ctx.db() as s:
                    s.get(Series, info["id"]).youtube_playlist_id = playlist_id
                    s.commit()

        replaces = None
        if prev_video and prev_digest == digest:
            video_id = prev_video  # 앞 시도에서 이미 올렸다 (재생목록에서 실패한 경우 등)
        else:
            title = (f"{info['title']} {info['number']}화: {info['episodeTitle']}" if info
                     else (script.get("titleCandidates") or [job["topic"]])[0])
            res = yt.upload_video(video, title=title, description=_description(script, playlist_id), disclosure=disclosure,
                                  category_id=str(ycfg.get("category_id", "28")),
                                  tags=[h.lstrip("#") for h in script.get("hashtags", [])], synthetic=synthetic)
            video_id, replaces = res["id"], prev_video
            with ctx.db() as s:  # 바로 남긴다: 뒤에서 실패해도 다시 올리지 않게
                pub = s.get(Publication, ctx.job_id) or Publication(job_id=ctx.job_id, platform="youtube", visibility="private")
                pub.video_id, pub.visibility = video_id, "private"
                pub.contains_synthetic_media, pub.uploaded_sha256 = synthetic, digest
                s.add(pub)
                s.commit()

        if playlist_id:
            yt.add_to_playlist(playlist_id, video_id)
        ctx.write_json("upload.json", {"videoId": video_id, "url": f"https://www.youtube.com/shorts/{video_id}",
                                       "privacy": "private", "containsSyntheticMedia": synthetic,
                                       "playlistId": playlist_id, "replaces": replaces, "sha256": digest})
