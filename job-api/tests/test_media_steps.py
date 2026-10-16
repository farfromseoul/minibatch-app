"""tts · timeline · visuals · render 단계 (앱 설계 "TTS", "타임라인 계산", D18).

tts-worker·render-worker 는 가짜 HTTP 서버로 대신한다. 같은 임시 폴더를 쓰므로 가짜 서버가 파일을 직접 쓴다.
"""
import json
import pathlib
import shutil
import threading
import unittest
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.pipeline.steps.media import RenderStep
from app.pipeline.timeline_calc import compute_timeline
from app.text.pronunciation import apply_pronunciation
from tests.fakes import FakeLlm, FakeRegistry
from tests.helpers import AppTestCase

REAL_CATEGORY = pathlib.Path(__file__).resolve().parents[1] / "content" / "categories" / "ai-it.yaml"
REAL_DICT = pathlib.Path(__file__).resolve().parents[1] / "content" / "pronunciation.yaml"


class FakeWorker(BaseHTTPRequestHandler):
    """POST /synthesize: 문장마다 seconds 길이 무음 WAV. POST /render: out 에 가짜 MP4."""
    seconds = 4.0
    status = 200
    received = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeWorker.received.append((self.path, body))
        if FakeWorker.status != 200:
            return self._send(FakeWorker.status, {"detail": "가짜 오류"})
        if self.path == "/synthesize":
            out = pathlib.Path(body["out_dir"])
            out.mkdir(parents=True, exist_ok=True)
            items = []
            for s in body["sentences"]:
                p = out / f"{s['id']}.wav"
                with wave.open(str(p), "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(8000)
                    w.writeframes(b"\x00\x00" * int(8000 * FakeWorker.seconds))
                items.append({"id": s["id"], "path": str(p), "seconds": FakeWorker.seconds})
            return self._send(200, {"sample_rate": 44100, "items": items})
        if self.path == "/render":
            out = pathlib.Path(body["out"])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"fake-mp4")
            return self._send(200, {"path": str(out), "frames": 1700, "renderSec": 40.0})
        self._send(404, {})

    def _send(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class Write:
    """정해진 내용을 쓰는 앞 단계 (script·review·scenes 대신)"""

    def __init__(self, name, inputs, files):
        self.name, self.inputs, self.outputs, self.files = name, inputs, list(files), files

    def run(self, ctx):
        for rel, content in self.files.items():
            ctx.write_json(rel, content)


def scenes_doc(lines_per_scene=(1, 3, 3, 3, 3)):
    scenes, n = [], 0
    comps = ["TitleReveal", "FlowDiagram", "ComparisonCards", "FlowDiagram", "SummaryScene"]
    props = {"TitleReveal": {"title": "RAG"},
             "FlowDiagram": {"nodes": [{"id": "a", "label": "질문"}, {"id": "b", "label": "검색"}], "edges": [["a", "b"]]},
             "ComparisonCards": {"left": {"title": "A", "points": ["x"]}, "right": {"title": "B", "points": ["y"]}},
             "SummaryScene": {"points": ["정리"]}}
    for i, k in enumerate(lines_per_scene, start=1):
        lines = []
        for _ in range(k):
            n += 1
            lines.append(f"RAG는 {n}번째 문장입니다.")
        scenes.append({"id": f"s{i:02d}", "role": "hook" if i == 1 else ("summary" if i == len(lines_per_scene) else "explain"),
                       "lines": lines, "visual": {"type": "template", "component": comps[i - 1], "props": props[comps[i - 1]]},
                       "animationPreset": "fade", "padAfterSec": 0.3})
    return {"schemaVersion": 1, "jobId": "x", "title": "제목", "scenes": scenes}


class MediaCase(AppTestCase):
    pipeline = ["topic", "script", "review", "scenes", "tts", "timeline", "visuals", "render"]

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeWorker)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeWorker.seconds, FakeWorker.status, FakeWorker.received = 4.0, 200, []
        super().setUp()
        shutil.copy(REAL_CATEGORY, self.settings.content_dir / "categories" / "ai-it.yaml")
        shutil.copy(REAL_DICT, self.settings.content_dir / "pronunciation.yaml")

    def extra_settings(self):
        return {"render_worker_url": self.url}

    def make_providers(self):
        return FakeRegistry(FakeLlm(), tts_url=self.url)

    def make_steps(self):
        self.normalized = []
        self.normalize_error = None

        def normalize(src, dst, **kw):  # 가짜 음량 맞추기: 받은 인자를 남기고 파일을 그대로 복사
            if self.normalize_error:
                raise self.normalize_error
            self.normalized.append((pathlib.Path(src), pathlib.Path(dst), kw))
            shutil.copy(src, dst)
            return {"input_i": "-25.5", "normalization_type": "dynamic"}

        return {
            "render": RenderStep(normalize=normalize),
            "script": Write("script", ["job.json"], {"script.json": {"titleCandidates": ["제목"]}}),
            "review": Write("review", ["script.json"], {"review.json": {"verdict": "pass"}}),
            "scenes": Write("scenes", ["script.json"], {"scenes.json": scenes_doc()}),
        }

    def read(self, job_id, name):
        return json.loads((self.job_dir(job_id) / name).read_text())

    def status(self, job_id, step):
        return self.get(f"/jobs/{job_id}/steps/{step}").json()


class PronunciationTest(unittest.TestCase):
    def test_replaces_whole_words_only(self):
        d = {"RAG": "래그", "API": "에이피아이", "LLM": "엘엘엠"}

        self.assertEqual(apply_pronunciation("RAG는 API로 LLM에 넘깁니다.", d), "래그는 에이피아이로 엘엘엠에 넘깁니다.")
        self.assertEqual(apply_pronunciation("DRAG 와 RAGS", d), "DRAG 와 RAGS")  # 다른 단어의 일부는 바꾸지 않는다

    def test_real_dictionary_loads(self):
        import yaml

        d = yaml.safe_load(REAL_DICT.read_text(encoding="utf-8"))
        self.assertIn("RAG", d["words"])


class TtsStepTest(MediaCase):
    def test_writes_wavs_and_tts_json_with_original_and_spoken_text(self):
        job_id = self.new_job()

        self.run_until(job_id, "tts")

        tts = self.read(job_id, "tts.json")
        self.assertEqual(len(tts["items"]), 13)
        first = tts["items"][0]
        self.assertEqual(first["id"], "s01-01")
        self.assertEqual(first["scene"], "s01")
        self.assertEqual(first["text"], "RAG는 1번째 문장입니다.")  # 자막용 원문
        self.assertTrue(first["spoken"].startswith("래그는"))  # TTS 입력은 발음 사전 적용
        self.assertEqual(first["path"], "tts/s01-01.wav")
        self.assertAlmostEqual(first["seconds"], 4.0)
        self.assertTrue((self.job_dir(job_id) / "tts" / "s01-01.wav").is_file())
        self.assertEqual([p.name for p in self.job_dir(job_id).iterdir() if "tmp" in p.name], [])

    def test_requests_category_voice_and_spoken_text(self):
        job_id = self.new_job()

        self.run_until(job_id, "tts")

        path, body = FakeWorker.received[-1]
        self.assertEqual(path, "/synthesize")
        self.assertEqual(body["voice"], "M1")  # ai-it.yaml voices.supertonic
        self.assertTrue(body["sentences"][0]["text"].startswith("래그는"))

    def test_worker_errors(self):
        for status, kind in ((500, "transient"), (400, "deterministic")):
            with self.subTest(status=status):
                FakeWorker.status = 200
                job_id = self.new_job(f"주제{status}")
                self.run_until(job_id, "scenes")
                FakeWorker.status = status

                self.run_step(job_id, "tts")

                self.assertEqual(self.status(job_id, "tts")["kind"], kind)
                self.assertFalse((self.job_dir(job_id) / "tts").exists())


class TimelineCalcTest(unittest.TestCase):
    def test_frames_follow_design_formula(self):
        scenes = {"scenes": [
            {"id": "s01", "lines": ["가"], "visual": {"type": "template", "component": "TitleReveal", "props": {"title": "t"}},
             "animationPreset": "pop", "padAfterSec": 0.3},
            {"id": "s02", "lines": ["나", "다"], "visual": {"type": "template", "component": "SummaryScene", "props": {"points": ["p"]}},
             "animationPreset": "fade", "padAfterSec": 0.3},
        ]}
        tts = {"items": [
            {"id": "s01-01", "scene": "s01", "text": "가", "path": "tts/s01-01.wav", "seconds": 2.0},
            {"id": "s02-01", "scene": "s02", "text": "나", "path": "tts/s02-01.wav", "seconds": 1.0},
            {"id": "s02-02", "scene": "s02", "text": "다", "path": "tts/s02-02.wav", "seconds": 1.5},
        ]}

        t = compute_timeline(scenes, tts, fps=30, width=1080, height=1920, theme="default")

        # s01: 0.2 + 2.0 + 0.3 = 2.5초 → 0~75 프레임. 문장 시작 0.2초 = 6프레임
        # s02: 2.5초 시작, 0.2 + 1.0 + 0.15 + 1.5 + 0.3 = 3.15초 → 끝 5.65초 = 170프레임
        self.assertEqual([(s["fromFrame"], s["durationInFrames"]) for s in t["scenes"]], [(0, 75), (75, 95)])
        self.assertEqual(t["durationInFrames"], 170)
        self.assertEqual(t["audio"], [{"src": "tts/s01-01.wav", "fromFrame": 6},
                                      {"src": "tts/s02-01.wav", "fromFrame": 81},
                                      {"src": "tts/s02-02.wav", "fromFrame": 116}])
        self.assertEqual(t["captions"][1], {"text": "나", "fromFrame": 81, "toFrame": 111})
        self.assertEqual(t["captions"][2]["toFrame"], 161)
        self.assertEqual(t["scenes"][1]["visual"]["component"], "SummaryScene")
        self.assertIsNone(t["bgm"])


class TimelineStepTest(MediaCase):
    def test_writes_timeline_when_length_is_in_range(self):
        job_id = self.new_job()  # 13문장 × 4초 + 여백 = 약 55.7초

        self.run_until(job_id, "timeline")

        t = self.read(job_id, "timeline.json")
        self.assertEqual(t["schemaVersion"], 1)
        self.assertTrue(55 * 30 <= t["durationInFrames"] <= 65 * 30)
        self.assertEqual(len(t["captions"]), 13)

    def test_too_short_fails_back_to_script(self):
        FakeWorker.seconds = 2.0
        job_id = self.new_job()
        for step in self.pipeline[:6]:
            self.run_step(job_id, step)

        st = self.status(job_id, "timeline")
        self.assertEqual((st["status"], st["kind"], st["retryFrom"]), ("failed", "deterministic", "script"))
        self.assertIn("초", st["error"])


class VisualsAndRenderTest(MediaCase):
    def test_full_chain_to_mp4(self):
        job_id = self.new_job()

        self.run_until(job_id, "render")

        self.assertEqual(self.read(job_id, "visuals.json")["clipEngine"], "none")
        self.assertTrue((self.job_dir(job_id) / "render" / "final.mp4").is_file())
        path, body = FakeWorker.received[-1]
        self.assertEqual(path, "/render")
        self.assertEqual(body["timeline"], str(self.job_dir(job_id) / "timeline.json"))
        self.assertEqual(body["out"], str(self.job_dir(job_id) / "render" / "final.mp4"))

    def test_render_normalizes_loudness_in_place(self):
        job_id = self.new_job()

        self.run_until(job_id, "render")

        final = self.job_dir(job_id) / "render" / "final.mp4"
        (src, dst, kw) = self.normalized[0]
        self.assertEqual((src, kw), (final, {"target_i": -14.0, "true_peak": -1.5}))
        self.assertNotEqual(dst, final)  # 임시 파일에 쓰고 이름을 바꾼다 (규칙 5)
        self.assertEqual(final.read_bytes(), b"fake-mp4")
        self.assertEqual([p.name for p in final.parent.iterdir()], ["final.mp4"])

    def test_normalize_failure_is_deterministic_from_render(self):
        import subprocess

        self.normalize_error = subprocess.CalledProcessError(1, ["ffmpeg"], stderr="Invalid data found")
        job_id = self.new_job()

        self.run_until(job_id, "render")

        st = self.status(job_id, "render")
        self.assertEqual((st["status"], st["kind"], st["retryFrom"]), ("failed", "deterministic", "render"))
        self.assertIn("음량", st["error"])

    def test_render_errors(self):
        for status, kind, retry_from in ((409, "transient", None), (500, "transient", None), (422, "deterministic", "scenes")):
            with self.subTest(status=status):
                FakeWorker.status = 200
                job_id = self.new_job(f"렌더{status}")
                self.run_until(job_id, "visuals")
                FakeWorker.status = status

                self.run_step(job_id, "render")

                st = self.status(job_id, "render")
                self.assertEqual((st["kind"], st["retryFrom"]), (kind, retry_from))
