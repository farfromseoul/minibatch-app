"""timeline 계산 (앱 설계 "타임라인 계산"). 모든 시각을 여기서 정수 프레임으로 확정한다.

장면 시작 = 이전 장면 끝
장면 안 문장 i 시작 = 장면 시작 + 앞 여백(0.2초) + 앞 문장들 길이 합 + 문장 간격(0.15초) × i
장면 길이 = 앞 여백 + 문장 길이 합 + 문장 간격 × (문장 수 − 1) + padAfterSec
"""
from __future__ import annotations

import math
from typing import Any

LEAD_SEC = 0.2
GAP_SEC = 0.15


def frame(t: float, fps: int) -> int:
    # 반올림은 "0.5 면 올림"으로 고정한다(파이썬 round 는 짝수 쪽으로 반올림). 부동소수 오차는 6자리에서 자른다
    return math.floor(round(t * fps, 6) + 0.5)


def compute_timeline(scenes_doc: dict[str, Any], tts: dict[str, Any], *, fps: int, width: int, height: int,
                     theme: str) -> dict[str, Any]:
    by_scene: dict[str, list[dict[str, Any]]] = {}
    for item in tts["items"]:
        by_scene.setdefault(item["scene"], []).append(item)
    out_scenes, audio, captions = [], [], []
    t = 0.0
    for sc in scenes_doc["scenes"]:
        start = t
        cur = start + LEAD_SEC
        items = by_scene.get(sc["id"], [])
        for i, item in enumerate(items):
            if i:
                cur += GAP_SEC
            audio.append({"src": item["path"], "fromFrame": frame(cur, fps)})
            captions.append({"text": item["text"], "fromFrame": frame(cur, fps), "toFrame": frame(cur + item["seconds"], fps)})
            cur += item["seconds"]
        t = cur + float(sc.get("padAfterSec", 0.3))
        out_scenes.append({"id": sc["id"], "fromFrame": frame(start, fps), "durationInFrames": frame(t, fps) - frame(start, fps),
                           "visual": sc["visual"], "animationPreset": sc["animationPreset"]})
    return {"schemaVersion": 1, "fps": fps, "width": width, "height": height, "durationInFrames": frame(t, fps),
            "theme": theme, "scenes": out_scenes, "audio": audio, "captions": captions, "bgm": None}
