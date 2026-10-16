"""문장·글자 수 (앱 설계 "길이 맞추기": 글자 수는 공백 제외)."""
from __future__ import annotations

from typing import Any


def count_chars(text: str) -> int:
    return len("".join(text.split()))


def script_sentences(script: dict[str, Any]) -> list[str]:
    """말하는 순서: (지난 이야기) → 후킹 → 설명 → 요약 → (다음 화 예고). 문장 = TTS 단위 = 자막 단위"""
    out = []
    if script.get("recap"):
        out.append(script["recap"])
    out.append(script["hook"])
    out.extend(script["body"])
    out.append(script["summary"])
    if script.get("nextTeaser"):
        out.append(script["nextTeaser"])
    return out


def same_sentence(a: str, b: str) -> bool:
    return " ".join(a.split()) == " ".join(b.split())
