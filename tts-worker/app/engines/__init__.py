"""TTS 엔진 구현. 엔진 이름으로 고른다 (providers.yaml 의 tts.providers.<이름>.engine)."""
from __future__ import annotations

from pathlib import Path

from .base import Engine


def load_engine(name: str, model_dir: Path, voice: str) -> Engine:
    if name == "supertonic":
        from .supertonic import SupertonicEngine  # onnxruntime 을 쓸 때만 불러온다

        return SupertonicEngine(model_dir=model_dir, voice=voice)
    raise ValueError(f"지원하지 않는 TTS 엔진: {name} (supertonic)")
