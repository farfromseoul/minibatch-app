"""문장·글자 수 (앱 설계 "길이 맞추기": 글자 수는 공백 제외)."""
from __future__ import annotations

import re

from typing import Any


def count_chars(text: str) -> int:
    return len("".join(text.split()))


def script_sentences(script: dict[str, Any]) -> list[str]:
    """말하는 순서: 후킹 → (지난 화 연결) → 설명 → 요약 → (다음 화 예고). 문장 = TTS 단위 = 자막 단위
    (2026-10-18: 지난 화 문장이 맨 앞이면 첫 문장이 질문이 아니라 과거 이야기로 시작해 어색했다)"""
    out = [script["hook"]]
    if script.get("recap"):
        out.append(script["recap"])
    out.extend(script["body"])
    out.append(script["summary"])
    if script.get("nextTeaser"):
        out.append(script["nextTeaser"])
    return out


REPEAT_PREFIX = 16  # 공백·문장부호를 뺀 앞부분이 이만큼 같으면 되풀이로 본다


def _bare(sentence: str) -> str:
    return re.sub(r"[\s\W_]+", "", sentence)


def repeated_sentences(sentences: list[str]) -> list[tuple[int, int]]:
    """같은 문장이나 앞부분이 길게 같은 문장의 쌍 (앞 번호, 뒤 번호). 2026-10-18 실제: recap 이 body 에 그대로 또 나옴,
    summary 가 body 첫 문장을 거의 그대로 되풀이"""
    bare = [_bare(s) for s in sentences]
    pairs = []
    for j in range(len(bare)):
        for i in range(j):
            a, b = bare[i], bare[j]
            if a and (a == b or (len(a) >= REPEAT_PREFIX and len(b) >= REPEAT_PREFIX and a[:REPEAT_PREFIX] == b[:REPEAT_PREFIX])):
                pairs.append((i, j))
                break
    return pairs


def same_sentence(a: str, b: str) -> bool:
    return " ".join(a.split()) == " ".join(b.split())
