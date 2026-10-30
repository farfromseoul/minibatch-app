"""목록형 쇼츠 자막 시각 (아키텍처 D42, 목록형쇼츠 아키텍처 "자막 시각 계산").

음성은 문장 단위로 만들고(억양이 자연스럽다), 자막은 몇 단어씩 끊어 보여 준다. 구절 경계는 글자 비율로 추정한 뒤
문장 WAV 안의 침묵(쉼) 가운데로 옮긴다. 단어 시각은 구절 안에서 글자 비율로 나눈다. 정렬 모델(Whisper) 없이 한다
(버린 대안: 구절마다 따로 합성 — 억양이 끊김, Whisper 단어 정렬 — 모델·메모리 추가).
표준 라이브러리만 쓴다(wave, array): tts-worker 는 16비트 PCM 모노를 쓴다(supertonic.py subtype=PCM_16).
"""
from __future__ import annotations

import array
import math
import re
import sys
import wave
from pathlib import Path
from typing import Callable, Optional

PHRASE_CHARS = 12      # 구절 하나의 최대 글자 수(공백 제외)
WINDOW_SEC = 0.01      # RMS 창
SILENCE_DB = -35.0     # 가장 큰 창보다 이만큼 작으면 침묵
MIN_GAP_SEC = 0.06     # 문장 안 쉼으로 볼 최소 길이
SNAP_SEC = 0.4         # 추정 경계에서 이 안의 쉼이면 그 자리로 옮긴다 (2026-10-30 실제 음성: 문장 끝이 느려 추정이 0.3초 넘게 앞섬)
COMMA_WEIGHT = 1.5     # 쉼표·물음표는 글자 1.5개만큼 시간을 쓴다(쉬는 몫)
BREAK_AFTER = (",", "?", "!", "，")
# 이어 주는 말끝(~면, ~고, ~서, ~데 …)이나 조사(이·가·은·는·을·를 …) 뒤에서 끊으면 구절이 뜻 단위로 나뉜다
# (참고 영상: "클로드 스킬이 / 10만 개가 넘는다는데", "하고 싶은 일을 말하면 / 맞는 스킬을 찾아서 깔아 줘요")
CONNECTIVE = ("면", "고", "서", "데", "니까", "지만", "는데", "려면", "도록")
PARTICLE = ("이", "가", "은", "는", "을", "를", "에", "로", "도", "와", "과", "의")
BONUS = {"comma": 40.0, "connective": 15.0, "particle": 10.0}
PHRASE_COST = 4.0  # 구절 하나를 더 만드는 비용 (너무 잘게 쪼개지 않게)


def chars(text: str) -> int:
    return len("".join(text.split()))


def _break_bonus(word: str) -> float:
    core = word.rstrip(".")
    if core.endswith(BREAK_AFTER):
        return BONUS["comma"]
    if core.endswith(CONNECTIVE):
        return BONUS["connective"]
    if core.endswith(PARTICLE) and not any(ch.isdigit() for ch in core):
        return BONUS["particle"]
    return 0.0


def split_phrases(text: str, max_chars: int = PHRASE_CHARS) -> list[list[str]]:
    """어절(띄어쓰기) 단위로 구절을 나눈다. 구절은 max_chars 이하(어절 하나가 더 길면 그대로), 길이는 고르게,
    쉼표·이어 주는 말끝·조사 뒤에서 끊을수록 좋게 본다 (동적 계획법: 비용 = (길이 − 고른 길이)² + 구절 비용 − 끊는 자리 보너스)"""
    words = text.split()
    if not words:
        return []
    lens = [chars(w) for w in words]
    total = sum(lens)
    ideal = total / max(1, math.ceil(total / max_chars))
    n = len(words)
    best = [0.0] + [math.inf] * n
    prev = [0] * (n + 1)
    for j in range(1, n + 1):
        size = 0
        for i in range(j - 1, -1, -1):
            size += lens[i]
            if size > max_chars and j - i > 1:
                break
            bonus = _break_bonus(words[j - 1]) if j < n else 0.0
            cost = best[i] + (size - ideal) ** 2 + PHRASE_COST - bonus
            if cost < best[j]:
                best[j], prev[j] = cost, i
    out, j = [], n
    while j > 0:
        out.append(words[prev[j]:j])
        j = prev[j]
    return out[::-1]


def syllables(word: str) -> float:
    """읽는 길이 추정(음절). 한글은 글자 하나, 영어 대문자 약자는 글자당 1.6(AI → 에이아이),
    그 밖 영어는 글자당 0.45(find → 파인드), 숫자는 자리당 1.2. 발음 사전이 있으면 바꾼 말로 센다"""
    n = 0.0
    for run in re.findall(r"[A-Z]{2,}(?![a-z])|[A-Za-z]+|\d+|[가-힣]|[^\sA-Za-z\d가-힣]", word):
        if run.isdigit():
            n += 1.2 * len(run)
        elif run.isascii() and run.isalpha():
            n += 1.6 * len(run) if run.isupper() and len(run) >= 2 else 0.45 * len(run)
        elif "가" <= run <= "힣":
            n += 1
    return n


def _weight(word: str, speak: Optional[Callable[[str], str]] = None) -> float:
    spoken = speak(word) if speak else word
    return max(1.0, syllables(spoken)) + (COMMA_WEIGHT if word.endswith(BREAK_AFTER) else 0)


def read_pcm16(path: Path) -> tuple[array.array, int]:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"16비트 PCM 이 아니다: {path.name}")
        rate, ch = w.getframerate(), w.getnchannels()
        data = array.array("h", w.readframes(w.getnframes()))
    if sys.byteorder == "big":
        data.byteswap()
    if ch > 1:  # 첫 채널만
        data = array.array("h", data[::ch])
    return data, rate


def _rms_windows(samples: array.array, rate: int) -> list[float]:
    n = max(1, int(rate * WINDOW_SEC))
    out = []
    for i in range(0, len(samples), n):
        win = samples[i:i + n]
        out.append(math.sqrt(sum(v * v for v in win) / len(win)) if len(win) else 0.0)
    return out


def analyze(samples: array.array, rate: int) -> tuple[float, float, list[tuple[float, float]]]:
    """(소리 시작 초, 소리 끝 초, 문장 안 쉼 [(시작, 끝)])"""
    rms = _rms_windows(samples, rate)
    peak = max(rms) if rms else 0.0
    total = len(samples) / rate if rate else 0.0
    if peak <= 0:
        return 0.0, total, []
    floor = peak * (10 ** (SILENCE_DB / 20))
    loud = [r > floor for r in rms]
    first = next((i for i, x in enumerate(loud) if x), 0)
    last = len(loud) - 1 - next((i for i, x in enumerate(reversed(loud)) if x), 0)
    gaps, start = [], None
    for i in range(first, last + 1):
        if not loud[i] and start is None:
            start = i
        elif loud[i] and start is not None:
            if (i - start) * WINDOW_SEC >= MIN_GAP_SEC:
                gaps.append((start * WINDOW_SEC, i * WINDOW_SEC))
            start = None
    return first * WINDOW_SEC, min(total, (last + 1) * WINDOW_SEC), gaps


def align(text: str, seconds: float, wav: Optional[Path] = None, emphasis: Optional[str] = None,
          max_chars: int = PHRASE_CHARS, speak: Optional[Callable[[str], str]] = None) -> list[dict]:
    """문장 하나의 자막 구절. 시각은 문장 음성 시작 기준 초.
    [{text, start, end, words: [{text, start, emphasis?}]}]. WAV 를 못 읽으면 읽는 길이 비율만으로 나눈다.
    speak: 어절을 TTS 가 실제로 읽는 말로 바꾸는 함수(발음 사전, 예: AI → 에이아이)"""
    phrases = split_phrases(text, max_chars) or [[text]]
    speech_start, speech_end, gaps = 0.0, seconds, []
    if wav is not None:
        try:
            samples, rate = read_pcm16(wav)
            speech_start, speech_end, gaps = analyze(samples, rate)
        except (OSError, ValueError, EOFError, wave.Error):
            pass
    span = max(0.01, speech_end - speech_start)
    weights = [sum(_weight(w, speak) for w in p) for p in phrases]
    total = sum(weights)
    # 구절 경계 추정 → 가까운 쉼 가운데로
    bounds, acc = [], 0.0
    for wgt in weights[:-1]:
        acc += wgt
        guess = speech_start + span * acc / total
        mids = [(a + b) / 2 for a, b in gaps]
        near = min(mids, key=lambda m: abs(m - guess), default=None)
        bounds.append(near if near is not None and abs(near - guess) <= SNAP_SEC else guess)
    edges = [speech_start] + sorted(bounds) + [speech_end]
    emph = _emphasis_words(phrases, emphasis)
    out = []
    for k, words in enumerate(phrases):
        a, b = edges[k], max(edges[k + 1], edges[k] + 0.05)
        wsum = sum(_weight(w, speak) for w in words)
        t, ws = a, []
        for j, w in enumerate(words):
            ws.append({"text": w, "start": round(t, 4), **({"emphasis": True} if (k, j) in emph else {})})
            t += (b - a) * _weight(w, speak) / wsum
        # 구절 표시는 다음 구절 시작까지 (첫 구절은 문장 처음부터: 소리 전 빈 화면이 없게)
        out.append({"text": " ".join(words), "start": round(0.0 if k == 0 else a, 4),
                    "end": round(seconds if k == len(phrases) - 1 else edges[k + 1], 4), "words": ws})
    return out


def _emphasis_words(phrases: list[list[str]], emphasis: Optional[str]) -> set[tuple[int, int]]:
    """강조할 말(한 어절 이상)이 들어 있는 어절 위치들. 괄호·문장부호는 무시하고 앞부분이 같으면 같은 말로 본다"""
    if not emphasis:
        return set()
    target = [_core(x) for x in emphasis.split() if _core(x)]
    flat = [(k, j, _core(w)) for k, p in enumerate(phrases) for j, w in enumerate(p)]
    for i in range(len(flat)):
        window = flat[i:i + len(target)]
        if len(window) == len(target) and all(w and (w.startswith(t) or t.startswith(w)) for (_, _, w), t in zip(window, target)):
            return {(k, j) for k, j, _ in window}
    return set()


def _core(word: str) -> str:
    return "".join(ch for ch in word if ch.isalnum())
