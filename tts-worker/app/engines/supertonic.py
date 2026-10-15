"""Supertonic 3 (ONNX) 엔진. 시작할 때 모델을 한 번 올려 두고 요청마다 합성한다 (앱 설계 "TTS 작업자")."""
from __future__ import annotations

import threading
from pathlib import Path

import soundfile as sf

from ..vendor.supertonic.helper import load_text_to_speech, load_voice_style

LANG = "ko"
TOTAL_STEP = 8  # 예제 기본값 (0주 차 비교와 같다)
SPEED = 1.05  # 예제 기본값


class SupertonicEngine:
    name = "supertonic"

    def __init__(self, model_dir: Path, voice: str):
        style_path = model_dir / "voice_styles" / f"{voice}.json"
        if not style_path.is_file():
            available = sorted(p.stem for p in (model_dir / "voice_styles").glob("*.json"))
            raise ValueError(f"목소리 {voice} 가 없다. 쓸 수 있는 목소리: {available}")
        self._tts = load_text_to_speech(str(model_dir / "onnx"))
        self._style = load_voice_style([str(style_path)])
        self.sample_rate = int(self._tts.sample_rate)
        self._lock = threading.Lock()  # ONNX 세션을 요청끼리 동시에 쓰지 않는다

    def synthesize(self, text: str, out_path: Path) -> float:
        with self._lock:
            wav, duration = self._tts(text, LANG, self._style, TOTAL_STEP, SPEED)
        samples = wav[0, : int(self.sample_rate * float(duration[0]))]
        sf.write(str(out_path), samples, self.sample_rate, subtype="PCM_16")
        return len(samples) / self.sample_rate
