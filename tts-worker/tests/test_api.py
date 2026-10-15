import json
import pathlib
import tempfile
import unittest
import wave

from fastapi.testclient import TestClient

from app.main import create_app


class FakeEngine:
    """문장 길이에 비례한 무음을 쓰는 가짜 엔진. 실제 모델 없이 API 계약만 시험한다."""

    name = "fake"
    sample_rate = 16000

    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def synthesize(self, text, out_path):
        self.calls.append(text)
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("합성 실패")
        frames = int(self.sample_rate * 0.1 * len(text))
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sample_rate)
            w.writeframes(b"\x00\x00" * frames)
        return frames / self.sample_rate


class ApiTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = pathlib.Path(self._tmp.name)
        self.engine = FakeEngine()
        self.client = TestClient(create_app(engine=self.engine, data_dir=self.data_dir))

    def tearDown(self):
        self._tmp.cleanup()


class HealthTest(ApiTestBase):
    def test_reports_engine_and_sample_rate(self):
        res = self.client.get("/healthz")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok", "engine": "fake", "sample_rate": 16000})


class SynthesizeTest(ApiTestBase):
    def body(self, **over):
        b = {"out_dir": str(self.data_dir / "jobs" / "j1" / "tts"),
             "sentences": [{"id": "s01", "text": "가나다"}, {"id": "s02", "text": "라마"}]}
        b.update(over)
        return b

    def test_writes_one_wav_per_sentence_and_returns_lengths(self):
        res = self.client.post("/synthesize", json=self.body())

        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["sample_rate"], 16000)
        self.assertEqual([i["id"] for i in data["items"]], ["s01", "s02"])
        for item, chars in zip(data["items"], (3, 2)):
            self.assertTrue(pathlib.Path(item["path"]).is_file())
            self.assertAlmostEqual(item["seconds"], 0.1 * chars, places=3)
        self.assertEqual(self.engine.calls, ["가나다", "라마"])

    def test_file_name_is_sentence_id(self):
        res = self.client.post("/synthesize", json=self.body())

        self.assertEqual(pathlib.Path(res.json()["items"][0]["path"]).name, "s01.wav")

    def test_rejects_out_dir_outside_data_dir(self):
        for bad in ("/etc", str(self.data_dir / ".." / "escape")):
            with self.subTest(out_dir=bad):
                res = self.client.post("/synthesize", json=self.body(out_dir=bad))

                self.assertEqual(res.status_code, 400)
        self.assertEqual(self.engine.calls, [])

    def test_rejects_unsafe_sentence_id(self):
        res = self.client.post("/synthesize", json=self.body(sentences=[{"id": "../x", "text": "가"}]))

        self.assertEqual(res.status_code, 422)

    def test_rejects_empty_sentence_list_and_blank_text(self):
        for sentences in ([], [{"id": "s01", "text": "   "}]):
            with self.subTest(sentences=sentences):
                res = self.client.post("/synthesize", json=self.body(sentences=sentences))

                self.assertEqual(res.status_code, 422)

    def test_rejects_duplicate_ids(self):
        res = self.client.post("/synthesize", json=self.body(
            sentences=[{"id": "s01", "text": "가"}, {"id": "s01", "text": "나"}]))

        self.assertEqual(res.status_code, 422)

    def test_engine_failure_returns_500_with_sentence_id(self):
        self.engine.fail_on = "라마"

        res = self.client.post("/synthesize", json=self.body())

        self.assertEqual(res.status_code, 500)
        self.assertIn("s02", res.json()["detail"])


if __name__ == "__main__":
    unittest.main()
