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
                     theme: str, phrases: Optional[dict[str, list[dict[str, Any]]]] = None,
                     spans: Optional[dict[str, tuple[float, float]]] = None,
                     pacing: Optional[dict[str, float]] = None) -> dict[str, Any]:
    """spans: 문장 WAV 안의 말 구간 (시작 초, 끝 초). 주면 앞뒤 무음을 잘라 문장 사이를 pacing 의 쉼으로 둔다
    (목록형 D42, 2026-10-31: Supertonic 이 문장마다 앞 0.6초·뒤 0.65초 무음을 붙여 문장 사이가 1.3초 넘게 비었다).
    음성 파일은 그대로 두고, 앞 무음만큼 일찍 틀어 말이 정한 시각에 시작하게 한다(무음끼리 겹쳐도 소리는 같다)"""
    scale = (pacing or {}).get("scale", 1.0)  # 쉼 배율 (목록형: 목표 길이에 맞추려고 쉼만 늘리고 줄인다, 2026-10-31)
    lead = (pacing or {}).get("lead", LEAD_SEC) * scale
    gap = (pacing or {}).get("gap", GAP_SEC) * scale
    tail = (pacing or {}).get("tail", 0.0)
    hold = (pacing or {}).get("hold", 0.0)
    by_scene: dict[str, list[dict[str, Any]]] = {}
    for item in tts["items"]:
        by_scene.setdefault(item["scene"], []).append(item)
    out_scenes, audio, captions = [], [], []
    t = 0.0
    for sc in scenes_doc["scenes"]:
        start = t
        cur = start + lead
        items = by_scene.get(sc["id"], [])
        for i, item in enumerate(items):
            if i:
                cur += gap
            span = (spans or {}).get(item["id"])
            if span:
                begin = cur - span[0]          # 음성 파일을 이만큼 일찍 튼다
                if begin < 0:                  # 영상 맨 앞이면 말 시작을 뒤로 민다
                    cur, begin = cur - begin, 0.0
                length = span[1] - span[0] + tail
            else:
                begin, length = cur, float(item["seconds"])
            audio.append({"src": item["path"], "fromFrame": frame(begin, fps)})
            chunks = (phrases or {}).get(item["id"])
            if chunks:
                captions.extend(_phrase_captions(chunks, begin, fps, lo=cur - 0.08, hi=cur + length,
                                                 floor=captions[-1]["toFrame"] if captions else 0))
            else:
                captions.append({"text": item["text"], "fromFrame": frame(cur, fps), "toFrame": frame(cur + length, fps)})
            cur += length
        t = cur + float(sc.get("padAfterSec", 0.3)) * scale
        out_scenes.append({"id": sc["id"], "fromFrame": frame(start, fps), "durationInFrames": frame(t, fps) - frame(start, fps),
                           "visual": sc["visual"], "animationPreset": sc["animationPreset"],
                           **({"section": sc["section"]} if sc.get("section") else {})})
    if hold:  # 짧은 쉼 동안은 앞 자막을 남겨 깜빡이지 않게
        for a, b in zip(captions, captions[1:]):
            if 0 < b["fromFrame"] - a["toFrame"] <= frame(hold, fps):
                a["toFrame"] = b["fromFrame"]
    out = {"schemaVersion": 1, "fps": fps, "width": width, "height": height, "durationInFrames": frame(t, fps),
           "theme": theme, "scenes": out_scenes, "audio": audio, "captions": captions, "bgm": None}
    if scenes_doc.get("tracker"):
        out["tracker"] = scenes_doc["tracker"]
    return out


def _phrase_captions(chunks: list[dict[str, Any]], base: float, fps: int, lo: float, hi: float,
                     floor: int = 0) -> list[dict[str, Any]]:
    """구절 자막(시각은 음성 파일 시작 base 기준). 말 구간 [lo, hi] 안으로 자르고, 차례대로·겹치지 않게
    (render 검사: 단어는 자막 안, 앞 단어 이후)"""
    out: list[dict[str, Any]] = []
    for c in chunks:
        a = max(frame(max(lo, base + c["start"]), fps), floor, out[-1]["toFrame"] if out else 0)
        b = frame(min(hi, base + c["end"]), fps)
        if b <= a:
            continue
        words, prev = [], a
        for w in c["words"]:
            f = min(b - 1, max(prev, frame(base + w["start"], fps)))
            words.append({"text": w["text"], "fromFrame": f, **({"emphasis": True} if w.get("emphasis") else {})})
            prev = f
        out.append({"text": c["text"], "fromFrame": a, "toFrame": b, "words": words})
    return out
