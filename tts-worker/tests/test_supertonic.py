"""실제 Supertonic 모델로 합성한다. 모델이 있는 이미지 안에서만 돈다 (없으면 건너뛴다).

0주 차 기준 문장(영어 약어, 숫자)을 쓴다 (앱 설계 "TTS 작업자").
"""
import os
import pathlib
import tempfile
import unittest

import soundfile as sf

MODEL_DIR = pathlib.Path(os.environ.get("MINIBATCH_TTS_MODEL_DIR", "/models/supertonic-3"))
HAS_MODEL = (MODEL_DIR / "onnx" / "vocoder.onnx").is_file()

WEEK0_SENTENCES = [
    "LLM이 모르는 걸 물어보면 어떻게 될까요?",
    "RAG는 먼저 관련 문서를 찾고, 그 내용을 API로 LLM에 넘깁니다.",
    "쿠버네티스는 2014년에 공개됐고, 지금은 컨테이너 3개든 300개든 똑같이 다룹니다.",
]


@unittest.skipUnless(HAS_MODEL, f"모델 없음: {MODEL_DIR}")
class SupertonicEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.engines import load_engine

        cls.engine = load_engine("supertonic", MODEL_DIR, "M1")

    def test_sample_rate_is_44100(self):
        self.assertEqual(self.engine.sample_rate, 44100)

    def test_week0_sentences_make_plausible_wavs(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i, text in enumerate(WEEK0_SENTENCES, start=1):
                with self.subTest(text=text):
                    path = pathlib.Path(tmp) / f"s{i:02d}.wav"

                    seconds = self.engine.synthesize(text, path)

                    info = sf.info(str(path))
                    self.assertEqual(info.samplerate, 44100)
                    self.assertEqual(info.channels, 1)
                    self.assertAlmostEqual(info.duration, seconds, places=2)
                    # 0주 차 실측 3.3~7.2초. 한 글자 0.05~0.5초 범위면 정상으로 본다
                    chars = len(text.replace(" ", ""))
                    self.assertTrue(0.05 * chars < seconds < 0.5 * chars, seconds)

    def test_unknown_voice_lists_available_ones(self):
        from app.engines import load_engine

        with self.assertRaises(ValueError) as ctx:
            load_engine("supertonic", MODEL_DIR, "없는목소리")
        self.assertIn("M1", str(ctx.exception))


class LoadEngineTest(unittest.TestCase):
    def test_unknown_engine_name(self):
        from app.engines import load_engine

        with self.assertRaises(ValueError):
            load_engine("nope", MODEL_DIR, "M1")


if __name__ == "__main__":
    unittest.main()
