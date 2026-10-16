"""ffprobe·ffmpeg 로 완성 영상을 잰다 (앱 설계 "품질 게이트"). job-api 이미지에 ffmpeg 가 들어 있다.

음량(ebur128)과 무음(silencedetect)은 오디오를 한 번만 읽도록 필터 하나로 잰다.
음량 맞추기(loudnorm)는 두 번 읽는다: 한 번 재고, 잰 값을 넣어 한 번 바꾼다(한 번에 하면 덜 정확하다).
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
_LOUDNORM_JSON = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}", re.S)


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


def parse_loudnorm(log: str) -> dict[str, str]:
    """loudnorm print_format=json 이 stderr 끝에 찍는 JSON"""
    m = _LOUDNORM_JSON.search(log)
    if not m:
        raise ValueError("loudnorm 측정 결과가 없다")
    return json.loads(m.group(0))


def normalize_loudness(src: Path, dst: Path, target_i: float = -14.0, true_peak: float = -1.5, lra: float = 11.0,
                       timeout: int = 600) -> dict[str, str]:
    """오디오만 target_i LUFS 로 맞춰 dst 에 쓴다. 영상은 다시 인코딩하지 않고 복사한다.

    작은 소리를 많이 키우면 순간 최대(true peak)가 한도를 넘어 loudnorm 이 dynamic 방식으로 바뀐다.
    2026-10-16 실제 1화: -25.5 → -14.0 LUFS, 최대 -1.4 dBFS, 영상 프레임 수 그대로.
    """
    base = f"loudnorm=I={target_i}:TP={true_peak}:LRA={lra}"
    first = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-vn", "-af", f"{base}:print_format=json",
                            "-f", "null", "-"], check=True, capture_output=True, text=True, timeout=timeout)
    m = parse_loudnorm(first.stderr)
    second = (f"{base}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
              f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true:print_format=json")
    run = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(src), "-map", "0:v", "-map", "0:a",
                          "-c:v", "copy", "-af", second, "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                          "-movflags", "+faststart", "-f", "mp4", str(dst)],
                         check=True, capture_output=True, text=True, timeout=timeout)
    out = parse_loudnorm(run.stderr)
    return {**m, "output_i": out.get("output_i"), "output_tp": out.get("output_tp"),
            "normalization_type": out.get("normalization_type")}
