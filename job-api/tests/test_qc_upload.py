"""qc · upload 단계 (앱 설계 "품질 게이트", "YouTube 게시", 아키텍처 D9·D26 ②).

ffmpeg 측정과 YouTube 는 가짜로 바꾼다. 실제 측정은 test_ffmpeg_real, 실제 요청 모양은 test_youtube_client 가 본다.
"""
import json
import pathlib
import shutil

from app.pipeline.steps.publishing import QcStep, UploadStep
from app.youtube.client import YouTubeError
from tests.helpers import AppTestCase

REAL_CATEGORY = pathlib.Path(__file__).resolve().parents[1] / "content" / "categories" / "ai-it.yaml"
DISCLOSURE = "AI 도구로 대본과 음성을 만들었습니다"


class FakeYouTube:
    def __init__(self):
        self.calls = []
        self.fail = {}  # 메서드 이름 → YouTubeError (한 번만)
        self.uploaded = 0
        self.playlist = {}

    def _maybe_fail(self, name):
        if name in self.fail:
            raise self.fail.pop(name)

    def upload_video(self, path, **kw):
        self._maybe_fail("upload_video")
        self.uploaded += 1
        self.calls.append(("upload_video", {"path": str(path), "bytes": pathlib.Path(path).read_bytes(), **kw}))
        return {"id": f"VID{self.uploaded}", "status": {"privacyStatus": "private", "uploadStatus": "uploaded"}}

    def create_playlist(self, title, description, privacy="public"):
        self._maybe_fail("create_playlist")
        self.calls.append(("create_playlist", {"title": title, "description": description}))
        pid = f"PL{len(self.playlist) + 1}"
        self.playlist[pid] = []
        return pid

    def add_to_playlist(self, playlist_id, video_id):
        self._maybe_fail("add_to_playlist")
        self.calls.append(("add_to_playlist", {"playlist": playlist_id, "video": video_id}))
        if video_id in self.playlist[playlist_id]:
            return False
        self.playlist[playlist_id].append(video_id)
        return True

    def set_privacy(self, video_id, privacy, publish_at=None):
        self._maybe_fail("set_privacy")
        self.calls.append(("set_privacy", {"video": video_id, "privacy": privacy, "publish_at": publish_at}))
        return {}

    def append_to_description(self, video_id, text, disclosure):
        self._maybe_fail("append_to_description")
        self.calls.append(("append_to_description", {"video": video_id, "text": text, "disclosure": disclosure}))
        return True

    def named(self, name):
        return [kw for n, kw in self.calls if n == name]


def good_analysis(**over):
    a = {"durationSec": 59.8, "video": {"codec": "h264", "width": 1080, "height": 1920, "fps": 30.0, "frames": 1794},
         "audio": [{"codec": "aac", "channels": 2, "sampleRate": 48000}], "integratedLufs": -14.5,
         "silences": [(25.2, 26.8)]}
    a.update(over)
    return a


class Write:
    def __init__(self, name, inputs, files):
        self.name, self.inputs, self.outputs, self.files = name, inputs, list(files), files

    def run(self, ctx):
        for rel, content in self.files.items():
            if isinstance(content, (bytes, str)):
                ctx.write_text(rel, content if isinstance(content, str) else content.decode())
            else:
                ctx.write_json(rel, content() if callable(content) else content)


def timeline(frames=1794):
    return {"schemaVersion": 1, "fps": 30, "width": 1080, "height": 1920, "durationInFrames": frames,
            "captions": [{"text": "가", "fromFrame": 6, "toFrame": 60}, {"text": "나", "fromFrame": 81, "toFrame": 111}],
            "scenes": [], "audio": [], "bgm": None}


SCRIPT = {"hook": "AI는 문제집을 푸는 학생이에요.", "summary": "학습은 패턴 찾기입니다.",
          "titleCandidates": ["AI는 어떻게 배울까?", "둘", "셋"], "hashtags": ["#AI", "#머신러닝"]}


class PublishCase(AppTestCase):
    pipeline = ["topic", "script", "timeline", "visuals", "render", "qc", "upload"]
    analysis = None
    video_bytes = "mp4-v1"
    clip = False

    def setUp(self):
        self.yt = FakeYouTube()
        self.analysis = good_analysis()
        super().setUp()
        shutil.copy(REAL_CATEGORY, self.settings.content_dir / "categories" / "ai-it.yaml")

    def make_youtube(self):
        return lambda settings: self.yt

    def make_steps(self):
        case = self
        return {
            "script": Write("script", ["job.json"], {"script.json": SCRIPT}),
            "timeline": Write("timeline", ["script.json"], {"timeline.json": timeline()}),
            "visuals": Write("visuals", ["timeline.json"], {"visuals.json": lambda: {
                "clipEngine": "none", "scenes": [{"id": "s01", "source": "clip" if case.clip else "template"}]}}),
            "render": RenderFake(case),
            "qc": QcStep(analyze=lambda path, **kw: case.analysis),
            "upload": UploadStep(youtube_factory=lambda settings: case.yt),
        }

    def status(self, job_id, step):
        return self.get(f"/jobs/{job_id}/steps/{step}").json()

    def read(self, job_id, name):
        return json.loads((self.job_dir(job_id) / name).read_text())


class RenderFake:
    name, inputs, outputs = "render", ["timeline.json", "visuals.json"], ["render/final.mp4"]

    def __init__(self, case):
        self.case = case

    def run(self, ctx):
        ctx.write_text("render/final.mp4", self.case.video_bytes)


class QcTest(PublishCase):
    def test_passes_and_writes_checks(self):
        job_id = self.new_job()

        self.run_until(job_id, "qc")

        qc = self.read(job_id, "qc.json")
        self.assertTrue(qc["passed"])
        self.assertEqual({c["name"] for c in qc["checks"]},
                         {"length", "resolution", "fps", "frames", "audio", "silence", "captions", "loudness"})
        self.assertEqual(qc["warnings"], [])
        self.assertTrue(all(c["ok"] for c in qc["checks"]))

    def test_length_out_of_range_goes_back_to_script(self):
        self.analysis = good_analysis(durationSec=66.3)
        job_id = self.new_job()

        self.run_until(job_id, "qc")

        st = self.status(job_id, "qc")
        self.assertEqual((st["status"], st["kind"], st["retryFrom"]), ("failed", "deterministic", "script"))
        self.assertIn("66.3", st["error"])
        self.assertFalse((self.job_dir(job_id) / "qc.json").exists())

    def test_long_silence_goes_back_to_tts(self):
        # 장면 사이 1.6~1.85초 무음은 정상이다(2026-10-16 실제 영상 3편). 음성이 빠진 경우만 잡는다
        self.analysis = good_analysis(silences=[(10.0, 11.85), (30.0, 33.1)])
        job_id = self.new_job()

        self.run_until(job_id, "qc")

        st = self.status(job_id, "qc")
        self.assertEqual((st["kind"], st["retryFrom"]), ("deterministic", "tts"))
        self.assertIn("3.1", st["error"])

    def test_stream_problems_go_back_to_render(self):
        cases = {"resolution": {"video": {"codec": "h264", "width": 720, "height": 1280, "fps": 30.0, "frames": 1794}},
                 "frames": {"video": {"codec": "h264", "width": 1080, "height": 1920, "fps": 30.0, "frames": 1700}},
                 "audio": {"audio": []}}
        for name, over in cases.items():
            with self.subTest(name=name):
                self.analysis = good_analysis(**over)
                job_id = self.new_job(f"주제 {name}")

                self.run_until(job_id, "qc")

                st = self.status(job_id, "qc")
                self.assertEqual((st["kind"], st["retryFrom"]), ("deterministic", "render"), name)

    def test_quiet_audio_goes_back_to_render(self):
        # render 단계가 -14 LUFS 로 맞추므로(20-d4), 어긋나면 음량 맞추기가 안 된 것이다
        self.analysis = good_analysis(integratedLufs=-25.5)
        job_id = self.new_job()

        self.run_until(job_id, "qc")

        st = self.status(job_id, "qc")
        self.assertEqual((st["kind"], st["retryFrom"]), ("deterministic", "render"))
        self.assertIn("음량 -25.5", st["error"])

    def test_caption_past_end_fails(self):
        self.analysis = good_analysis()
        self.steps["timeline"].files["timeline.json"] = timeline(frames=100)  # 자막이 111프레임까지
        self.analysis = good_analysis(durationSec=59.8, video={"codec": "h264", "width": 1080, "height": 1920, "fps": 30.0, "frames": 100})
        job_id = self.new_job()

        self.run_until(job_id, "qc")

        st = self.status(job_id, "qc")
        self.assertEqual(st["kind"], "deterministic")
        self.assertIn("자막", st["error"])


class UploadTest(PublishCase):
    def test_uploads_private_with_metadata_and_goes_to_review(self):
        job_id = self.new_job()

        self.run_until(job_id, "upload")

        self.assertEqual(self.get(f"/jobs/{job_id}").json()["status"], "REVIEW")
        (call,) = self.yt.named("upload_video")
        self.assertEqual(call["title"], "AI는 어떻게 배울까?")
        self.assertEqual(call["disclosure"], DISCLOSURE)  # 카테고리 파일 youtube.disclosure
        self.assertEqual(call["category_id"], "28")
        self.assertEqual(call["tags"], ["AI", "머신러닝"])
        self.assertFalse(call["synthetic"])
        self.assertIn("AI는 문제집을 푸는 학생이에요.", call["description"])
        self.assertIn("#AI #머신러닝", call["description"])
        self.assertEqual(call["bytes"], b"mp4-v1")
        up = self.read(job_id, "upload.json")
        self.assertEqual((up["videoId"], up["privacy"], up["playlistId"]), ("VID1", "private", None))
        self.assertEqual(up["url"], "https://www.youtube.com/shorts/VID1")
        pub = self.get(f"/jobs/{job_id}").json()["publication"]
        self.assertEqual((pub["videoId"], pub["visibility"], pub["containsSyntheticMedia"]), ("VID1", "private", False))

    def test_clip_scene_marks_synthetic(self):
        self.clip = True
        job_id = self.new_job()

        self.run_until(job_id, "upload")

        self.assertTrue(self.yt.named("upload_video")[0]["synthetic"])

    def test_quota_waits_with_retry_time(self):
        self.yt.fail["upload_video"] = YouTubeError("quota", "업로드 한도", 403, "uploadLimitExceeded")
        job_id = self.new_job()

        self.run_until(job_id, "upload")

        st = self.status(job_id, "upload")
        self.assertEqual(st["kind"], "quota")
        self.assertTrue(st["retryAt"].endswith("Z"))
        self.assertEqual(self.get(f"/jobs/{job_id}").json()["status"], "WAITING")
        # n8n 생산 워크플로는 작업 상세 하나로 다음 행동을 정한다 (다시 할 시각 포함)
        last = self.get(f"/jobs/{job_id}").json()["steps"][-1]
        self.assertEqual((last["step"], last["retryAt"]), ("upload", st["retryAt"]))

    def test_expired_token_is_deterministic(self):
        self.yt.fail["upload_video"] = YouTubeError("deterministic", "갱신 토큰을 쓸 수 없다(invalid_grant) 15번")
        job_id = self.new_job()

        self.run_until(job_id, "upload")

        st = self.status(job_id, "upload")
        self.assertEqual((st["kind"], self.get(f"/jobs/{job_id}").json()["status"]), ("deterministic", "FAILED"))
        self.assertIn("15번", st["error"])

    def test_retry_after_partial_failure_does_not_upload_twice(self):
        series_job = self._series_job()
        self.yt.fail["add_to_playlist"] = YouTubeError("transient", "재생목록 연결 실패")

        self.run_until(series_job, "upload")
        self.assertEqual(self.status(series_job, "upload")["kind"], "transient")
        self.run_step(series_job, "upload")

        self.assertEqual(self.status(series_job, "upload")["status"], "succeeded")
        self.assertEqual(self.yt.uploaded, 1)  # 영상은 한 번만 올라간다 (DB 의 영상 ID·파일 해시)
        self.assertEqual(self.yt.playlist["PL1"], ["VID1"])

    def test_rerendered_video_is_uploaded_again(self):
        job_id = self.new_job()
        self.run_until(job_id, "upload")
        self.post(f"/jobs/{job_id}/reset?from=render")
        self.video_bytes = "mp4-v2"

        for step in ("render", "qc", "upload"):
            self.run_step(job_id, step)

        self.assertEqual(self.yt.uploaded, 2)
        up = self.read(job_id, "upload.json")
        self.assertEqual((up["videoId"], up["replaces"]), ("VID2", "VID1"))  # 앞 영상은 비공개로 남는다

    def test_missing_token_file_fails_with_procedure_hint(self):
        self.steps["upload"] = UploadStep()  # 실제 연결부: 설정의 파일 경로를 읽는다 (테스트에는 없다)
        self.app.state.runner.steps["upload"] = self.steps["upload"]
        job_id = self.new_job()

        self.run_until(job_id, "upload")

        st = self.status(job_id, "upload")
        self.assertEqual(st["kind"], "deterministic")
        self.assertIn("15번", st["error"])

    # 시리즈 (D26 ②)

    def _series_job(self, key="ai-office"):
        if self.get(f"/series/{key}").status_code == 404:
            res = self.post("/series", {"key": key, "title": "신입 개발자 민지의 AI 적응기",
                                        "bible": {"premise": "신입 개발자 민지가 매화 개념 하나씩 배운다"},
                                        "episodes": [{"number": 1, "title": "AI는 어떻게 배울까", "outline": "학습"},
                                                     {"number": 2, "title": "AI는 어떻게 판단할까", "outline": "추론"}]})
            self.assertEqual(res.status_code, 201, res.text)
        res = self.post("/jobs", {"seriesId": key})
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()["id"]

    def test_series_episode_title_playlist_and_link(self):
        job_id = self._series_job()

        self.run_until(job_id, "upload")

        call = self.yt.named("upload_video")[0]
        self.assertEqual(call["title"], "신입 개발자 민지의 AI 적응기 1화: AI는 어떻게 배울까")
        self.assertIn("https://www.youtube.com/playlist?list=PL1", call["description"])
        self.assertEqual(self.yt.named("create_playlist"), [{"title": "신입 개발자 민지의 AI 적응기",
                                                             "description": "신입 개발자 민지가 매화 개념 하나씩 배운다"}])
        self.assertEqual(self.yt.playlist["PL1"], ["VID1"])
        self.assertEqual(self.read(job_id, "upload.json")["playlistId"], "PL1")
        self.assertEqual(self.get("/series/ai-office").json()["playlistId"], "PL1")

    def test_second_episode_reuses_playlist(self):
        ep1 = self._series_job()
        self.run_until(ep1, "upload")
        self.assertEqual(self.post(f"/jobs/{ep1}/approve", {"approvedBy": "운영자"}).status_code, 200)
        ep2 = self._series_job()

        self.run_until(ep2, "upload")

        self.assertEqual(len(self.yt.named("create_playlist")), 1)
        self.assertEqual(self.yt.playlist["PL1"], ["VID1", "VID2"])
        self.assertTrue(self.yt.named("upload_video")[1]["title"].endswith("2화: AI는 어떻게 판단할까"))
