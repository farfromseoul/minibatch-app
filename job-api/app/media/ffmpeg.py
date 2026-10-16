"""ffprobe·ffmpeg 로 완성 영상을 잰다 (앱 설계 "품질 게이트"). job-api 이미지에 ffmpeg 가 들어 있다.

음량(ebur128)과 무음(silencedetect)은 오디오를 한 번만 읽도록 필터 하나로 잰다.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

_SILENCE_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*(-?[\d.]+)")
_SUMMARY_I = re.compile(r"Summary:.*?I:\s*(-?[\d.]+|-inf)\s*LUFS", re.S)


def parse_silences(log: str, end: float) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    start: Optional[float] = None
    for line in log.splitlines():
        if (m := _SILENCE_START.search(line)):
            start = float(m.group(1))
        elif (m := _SILENCE_END.search(line)) and start is not None:
            out.append((start, float(m.group(1))))
            start = None
    if start is not None:  # 끝까지 무음
        out.append((start, end))
    return out


def parse_ebur128(log: str) -> Optional[float]:
    m = _SUMMARY_I.search(log)
    if not m or m.group(1) == "-inf":
        return None
    return float(m.group(1))


def _fps(rate: str) -> float:
    num, _, den = rate.partition("/")
    return float(num) / float(den) if den and float(den) else float(num)


def analyze(path: Path, silence_db: int = -50, silence_min_sec: float = 1.5, timeout: int = 300) -> dict[str, Any]:
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        check=True, capture_output=True, text=True, timeout=timeout).stdout)
    duration = float(probe["format"]["duration"])
    video = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
    audio = [s for s in probe["streams"] if s["codec_type"] == "audio"]
    log = ""
    if audio:
        log = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn",
             "-af", f"ebur128,silencedetect=noise={silence_db}dB:d={silence_min_sec}", "-f", "null", "-"],
            check=True, capture_output=True, text=True, timeout=timeout).stderr
    v = None
    if video:
        fps = _fps(video.get("r_frame_rate", "0/1"))
        frames = int(video["nb_frames"]) if str(video.get("nb_frames", "")).isdigit() else round(float(video.get("duration", duration)) * fps)
        v = {"codec": video["codec_name"], "width": video["width"], "height": video["height"], "fps": fps, "frames": frames}
    return {
        "durationSec": duration,
        "video": v,
        "audio": [{"codec": s["codec_name"], "channels": s.get("channels"), "sampleRate": int(s.get("sample_rate", 0))} for s in audio],
        "integratedLufs": parse_ebur128(log),
        "silences": parse_silences(log, duration),
    }
