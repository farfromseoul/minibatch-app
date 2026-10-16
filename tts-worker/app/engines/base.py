from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol


class Engine(Protocol):
    """문장 하나를 WAV 파일 하나로 만든다. 길이(초)를 돌려준다."""

    name: str
    sample_rate: int

    def has_voice(self, voice: str) -> bool: ...

    def synthesize(self, text: str, out_path: Path, voice: Optional[str] = None) -> float:
        """voice 가 없으면 엔진 기본 목소리 (MINIBATCH_TTS_VOICE)"""
        ...
