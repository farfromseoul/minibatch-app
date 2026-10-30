"""timeline 계산 (앱 설계 "타임라인 계산"). 모든 시각을 여기서 정수 프레임으로 확정한다.

장면 시작 = 이전 장면 끝
장면 안 문장 i 시작 = 장면 시작 + 앞 여백(0.2초) + 앞 문장들 길이 합 + 문장 간격(0.15초) × i
장면 길이 = 앞 여백 + 문장 길이 합 + 문장 간격 × (문장 수 − 1) + padAfterSec

목록형(D42): phrases 를 주면 문장 하나를 자막 구절 여러 개(단어 시각 포함)로 나눈다(app/media/align.py 가 문장 시작 기준 초로 계산).
장면의 section, 문서의 tracker 는 그대로 넘긴다.
"""
from __future__ import annotations

import math
from typing import Any, Optional

LEAD_SEC = 0.2
GAP_SEC = 0.15


def frame(t: float, fps: int) -> int:
    # 반올림은 "0.5 면 올림"으로 고정한다(파이썬 round 는 짝수 쪽으로 반올림). 부동소수 오차는 6자리에서 자른다
    return math.floor(round(t * fps, 6) + 0.5)


def compute_timeline(scenes_doc: dict[str, Any], tts: dict[str, Any], *, fps: int, width: int, height: int,
                     theme: str, phrases: Optional[dict[str, list[dict[str, Any]]]] = None) -> dict[str, Any]:
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
            chunks = (phrases or {}).get(item["id"])
            if chunks:
                captions.extend(_phrase_captions(chunks, cur, fps))
            else:
                captions.append({"text": item["text"], "fromFrame": frame(cur, fps), "toFrame": frame(cur + item["seconds"], fps)})
            cur += item["seconds"]
        t = cur + float(sc.get("padAfterSec", 0.3))
        out_scenes.append({"id": sc["id"], "fromFrame": frame(start, fps), "durationInFrames": frame(t, fps) - frame(start, fps),
                           "visual": sc["visual"], "animationPreset": sc["animationPreset"],
                           **({"section": sc["section"]} if sc.get("section") else {})})
    out = {"schemaVersion": 1, "fps": fps, "width": width, "height": height, "durationInFrames": frame(t, fps),
           "theme": theme, "scenes": out_scenes, "audio": audio, "captions": captions, "bgm": None}
    if scenes_doc.get("tracker"):
        out["tracker"] = scenes_doc["tracker"]
    return out


def _phrase_captions(chunks: list[dict[str, Any]], base: float, fps: int) -> list[dict[str, Any]]:
    """구절 자막. 프레임으로 바꾼 뒤에도 차례대로·겹치지 않게(render 검사: 단어는 자막 안, 앞 단어 이후)"""
    out = []
    for c in chunks:
        a, b = frame(base + c["start"], fps), frame(base + c["end"], fps)
        if out and a < out[-1]["toFrame"]:
            a = out[-1]["toFrame"]
        if b <= a:
            continue
        words, prev = [], a
        for w in c["words"]:
            f = min(b - 1, max(prev, frame(base + w["start"], fps)))
            words.append({"text": w["text"], "fromFrame": f, **({"emphasis": True} if w.get("emphasis") else {})})
            prev = f
        out.append({"text": c["text"], "fromFrame": a, "toFrame": b, "words": words})
    return out
