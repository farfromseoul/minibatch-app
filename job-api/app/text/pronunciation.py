"""발음 사전 적용 (앱 설계 "TTS": TTS 입력만 바꾸고 자막은 원문)."""
from __future__ import annotations

import re
from pathlib import Path

import yaml


def load_dictionary(path: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    words = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("words", {}) if path.is_file() else {}
    return {**words, **(extra or {})}


def apply_pronunciation(text: str, words: dict[str, str]) -> str:
    # 긴 단어부터 바꾼다. 앞뒤가 영문·숫자가 아닐 때만 (다른 단어의 일부는 그대로)
    for word in sorted(words, key=len, reverse=True):
        text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", words[word], text)
    return text
