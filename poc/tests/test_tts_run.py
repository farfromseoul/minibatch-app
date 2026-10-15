import pathlib
import tempfile
import unittest
import wave

from tts_compare.run import SAMPLE_SENTENCES, render_markdown, run_engine, wav_seconds


def write_silence(path, seconds, rate=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))


class WavSecondsTest(unittest.TestCase):
    def test_reads_duration_from_wav_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "a.wav"
            write_silence(path, 1.5)

            self.assertAlmostEqual(wav_seconds(path), 1.5, places=3)


class RunEngineTest(unittest.TestCase):
    def test_writes_one_wav_per_sentence_and_measures_speed(self):
        def fake_synth(text, out_path):
            write_silence(out_path, 2.0)

        with tempfile.TemporaryDirectory() as tmp:
            records = run_engine("fake", fake_synth, ["가", "나"], pathlib.Path(tmp))

            self.assertEqual(len(records), 2)
            self.assertTrue(all(pathlib.Path(r["file"]).exists() for r in records))
            self.assertTrue(all(abs(r["audio_sec"] - 2.0) < 0.01 for r in records))
            self.assertTrue(all(r["rtf"] is not None and r["rtf"] >= 0 for r in records))

    def test_records_error_and_continues(self):
        def broken(text, out_path):
            raise RuntimeError("모델 없음")

        with tempfile.TemporaryDirectory() as tmp:
            records = run_engine("broken", broken, ["가", "나"], pathlib.Path(tmp))

        self.assertEqual(len(records), 2)
        self.assertTrue(all("모델 없음" in r["error"] for r in records))


class SampleSentencesTest(unittest.TestCase):
    def test_covers_plain_english_terms_and_numbers(self):
        joined = " ".join(SAMPLE_SENTENCES)

        self.assertTrue(any(ch.isdigit() for ch in joined))
        self.assertIn("RAG", joined)


class RenderMarkdownTest(unittest.TestCase):
    def test_one_row_per_engine_with_realtime_factor(self):
        records = [
            {"engine": "a", "audio_sec": 2.0, "synth_sec": 1.0, "rtf": 0.5, "error": None},
            {"engine": "a", "audio_sec": 2.0, "synth_sec": 1.0, "rtf": 0.5, "error": None},
            {"engine": "b", "audio_sec": None, "synth_sec": 0.1, "rtf": None, "error": "실패"},
        ]

        text = render_markdown(records)

        rows = [l for l in text.splitlines() if l.startswith("| a") or l.startswith("| b")]
        self.assertEqual(len(rows), 2)
        self.assertIn("0.50", text)
        self.assertIn("0/1", text.split("| b")[1])  # b 는 1건 중 0건 성공


if __name__ == "__main__":
    unittest.main()
