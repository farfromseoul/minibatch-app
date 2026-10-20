"""ASMR 채널: 폴더에 넣은 영상을 텔레그램 승인 두 번으로 올리고 공개한다 (아키텍처 D38, ASMR쇼츠 기획서 2026-10-20).

inbox 확인 → [업로드 승인] → 비공개 업로드(합성 콘텐츠 표시) → [공개 승인] → 공개.
파일은 상태에 따라 inbox → uploaded → published, 버리면 rejected 로 옮긴다.
"""
import pathlib
import subprocess
import tempfile
import unicodedata
import unittest

from app.asmr import service as asmr_service
from app.media.ffmpeg import probe_video
from app.youtube.client import YouTubeError
from tests.test_telegram import CHAT, TelegramCase

GOOD = {"durationSec": 8.0, "width": 1080, "height": 1920, "audio": True}


class FakeAsmrYouTube:
    def __init__(self):
        self.calls = []
        self.fail = {}
        self.channel = "UC-asmr"

    def _maybe_fail(self, name):
        if name in self.fail:
            raise self.fail.pop(name)

    def my_channel_id(self):
        self.calls.append(("my_channel_id", {}))
        return self.channel

    def upload_video(self, path, **kw):
        self._maybe_fail("upload_video")
        n = len([c for c in self.calls if c[0] == "upload_video"]) + 1
        self.calls.append(("upload_video", {"path": str(path), **kw}))
        return {"id": f"AVID{n}"}

    def set_privacy(self, video_id, privacy, publish_at=None):
        self._maybe_fail("set_privacy")
        self.calls.append(("set_privacy", {"video": video_id, "privacy": privacy}))
        return {}

    def called(self, name):
        return [kw for n, kw in self.calls if n == name]


class AsmrCase(TelegramCase):
    def setUp(self):
        self.yt = FakeAsmrYouTube()
        self.probes = {}  # 파일 이름 → ffprobe 결과 (없으면 GOOD)
        super().setUp()
        self.root = self.settings.data_dir / "asmr"
        (self.root / "inbox").mkdir(parents=True, exist_ok=True)

    def extra_settings(self):
        return {"asmr_channel_id": "UC-asmr"}

    def make_asmr_youtube(self):
        return lambda settings: self.yt

    def make_asmr_probe(self):
        return lambda path: dict(self.probes.get(pathlib.Path(path).name, GOOD))

    def put(self, name, text=None, folder="inbox"):
        p = self.root / folder / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fake-mp4")
        if text is not None:
            p.with_suffix(".txt").write_text(text, encoding="utf-8")
        return p

    def scan(self):
        res = self.post("/asmr/scan")
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    def video(self, vid):
        return self.get(f"/asmr/videos/{vid}").json()

    def files(self, folder):
        return sorted(p.name for p in (self.root / folder).glob("*")) if (self.root / folder).exists() else []

    def videos_sent(self):
        return self.tg.sent("sendVideo")

    def last_text(self):
        msgs = self.tg.sent("sendMessage")
        return msgs[-1]["text"] if msgs else ""


class ScanTest(AsmrCase):
    def test_new_file_asks_upload_approval_with_preview(self):
        self.put("20261020-01_젤리 키보드 ASMR.mp4")

        res = self.scan()

        self.assertEqual(res["found"], 1)
        v = self.video("asmr-20261020-01")
        self.assertEqual((v["status"], v["title"]), ("WAITING_UPLOAD", "젤리 키보드 ASMR"))
        (sent,) = self.videos_sent()
        raw = sent["_raw"].decode("utf-8", errors="ignore")
        self.assertIn("젤리 키보드 ASMR", raw)
        self.assertIn("ua:asmr-20261020-01", raw)
        self.assertIn("ux:asmr-20261020-01", raw)

    def test_same_file_is_not_asked_twice(self):
        self.put("20261020-01_젤리.mp4")
        self.scan()
        self.scan()

        self.assertEqual(len(self.videos_sent()), 1)

    def test_files_being_sent_are_ignored(self):
        self.put("20261020-01_젤리.mp4", folder="inbox/.incoming")
        self.put(".20261020-02_젤리.mp4.abc123")

        self.assertEqual(self.scan()["found"], 0)

    def test_bad_name_is_moved_to_rejected_and_explained(self):
        self.put("젤리 키보드.mp4")

        self.scan()

        self.assertEqual(self.files("rejected"), ["젤리 키보드.mp4"])
        self.assertIn("이름 규칙", self.last_text())

    def test_horizontal_or_long_video_is_not_uploaded(self):
        self.put("20261020-01_가로.mp4")
        self.put("20261020-02_김.mp4")
        self.probes = {"20261020-01_가로.mp4": dict(GOOD, width=1920, height=1080),
                       "20261020-02_김.mp4": dict(GOOD, durationSec=75.0)}

        self.scan()

        self.assertEqual([self.video(i)["status"] for i in ("asmr-20261020-01", "asmr-20261020-02")], ["INVALID", "INVALID"])
        self.assertEqual(self.files("rejected"), ["20261020-01_가로.mp4", "20261020-02_김.mp4"])
        texts = " ".join(m["text"] for m in self.tg.sent("sendMessage"))
        self.assertIn("세로", texts)
        self.assertIn("60초", texts)

    def test_decomposed_korean_name_is_normalized(self):
        self.put(unicodedata.normalize("NFD", "20261020-01_젤리 사탕.mp4"))

        self.scan()

        self.assertEqual(self.video("asmr-20261020-01")["title"], "젤리 사탕")

    def test_large_file_sends_text_instead_of_video(self):
        self.put("20261020-01_큰 파일.mp4")
        old = asmr_service.TELEGRAM_VIDEO_MAX_BYTES
        asmr_service.TELEGRAM_VIDEO_MAX_BYTES = 3
        try:
            self.scan()
        finally:
            asmr_service.TELEGRAM_VIDEO_MAX_BYTES = old

        self.assertEqual(self.videos_sent(), [])
        msg = self.tg.sent("sendMessage")[-1]
        self.assertEqual([b["callback_data"] for b in msg["reply_markup"]["inline_keyboard"][0]],
                         ["ua:asmr-20261020-01", "ux:asmr-20261020-01"])


class FlowTest(AsmrCase):
    def ready(self, name="20261020-01_젤리 키보드 ASMR.mp4", text=None):
        self.put(name, text)
        self.scan()
        return "asmr-" + name[:11]

    def test_upload_approval_uploads_private_with_synthetic_flag(self):
        vid = self.ready(text="키보드 위 과일 젤리\n#ASMR")
        self.tg.press(f"ua:{vid}")

        self.poll()

        (up,) = self.yt.called("upload_video")
        self.assertEqual(up["title"], "젤리 키보드 ASMR")
        self.assertTrue(up["synthetic"])
        self.assertIn("키보드 위 과일 젤리", up["description"])
        self.assertTrue(up["disclosure"].strip())
        v = self.video(vid)
        self.assertEqual((v["status"], v["videoId"]), ("UPLOADED", "AVID1"))
        self.assertEqual(self.files("uploaded"), ["20261020-01_젤리 키보드 ASMR.mp4", "20261020-01_젤리 키보드 ASMR.txt"])
        last = self.tg.sent("sendMessage")[-1]
        self.assertIn("https://www.youtube.com/shorts/AVID1", last["text"])
        self.assertEqual([b["callback_data"] for b in last["reply_markup"]["inline_keyboard"][0]], [f"up:{vid}", f"ux:{vid}"])

    def test_publish_approval_makes_it_public(self):
        vid = self.ready()
        self.tg.press(f"ua:{vid}")
        self.poll()
        self.tg.press(f"up:{vid}")

        self.poll()

        self.assertEqual(self.yt.called("set_privacy"), [{"video": "AVID1", "privacy": "public"}])
        self.assertEqual(self.video(vid)["status"], "PUBLISHED")
        self.assertEqual(self.files("published"), ["20261020-01_젤리 키보드 ASMR.mp4"])

    def test_reject_before_upload_moves_file_and_never_uploads(self):
        vid = self.ready()
        self.tg.press(f"ux:{vid}")

        self.poll()

        self.assertEqual(self.video(vid)["status"], "REJECTED")
        self.assertEqual(self.files("rejected"), ["20261020-01_젤리 키보드 ASMR.mp4"])
        self.assertEqual(self.yt.called("upload_video"), [])

    def test_publish_before_upload_is_refused_and_button_stays(self):
        vid = self.ready()
        self.tg.press(f"up:{vid}")

        self.poll()

        self.assertEqual(self.video(vid)["status"], "WAITING_UPLOAD")
        self.assertEqual(self.tg.sent("editMessageText"), [])

    def test_daily_limit_moves_extra_upload_to_next_day(self):
        ids = [self.ready(f"20261020-0{i}_젤리 {i}.mp4") for i in range(1, 5)]
        for vid in ids:
            self.tg.press(f"ua:{vid}")
        self.poll()

        self.assertEqual([self.video(v)["status"] for v in ids], ["UPLOADED"] * 3 + ["QUEUED"])
        self.assertIn("내일", self.last_text())

        self.clock.advance(days=1)
        self.scan()
        self.assertEqual(self.video(ids[3])["status"], "UPLOADED")

    def test_wrong_channel_token_never_uploads(self):
        self.yt.channel = "UC-minibatch"
        vid = self.ready()
        self.tg.press(f"ua:{vid}")

        self.poll()

        self.assertEqual(self.yt.called("upload_video"), [])
        self.assertEqual(self.video(vid)["status"], "FAILED")
        self.assertIn("채널", self.last_text())

    def test_quota_waits_and_retries_later(self):
        self.yt.fail["upload_video"] = YouTubeError("quota", "한도", 400, "uploadLimitExceeded")
        vid = self.ready()
        self.tg.press(f"ua:{vid}")
        self.poll()
        self.assertEqual(self.video(vid)["status"], "QUEUED")

        self.scan()  # 아직 다시 할 시각 전
        self.assertEqual(len(self.yt.called("upload_video")), 0)
        self.clock.advance(hours=1, minutes=1)
        self.scan()

        self.assertEqual(self.video(vid)["status"], "UPLOADED")

    def test_list_by_status(self):
        self.ready()

        items = self.get("/asmr/videos?status=WAITING_UPLOAD").json()["items"]

        self.assertEqual([i["id"] for i in items], ["asmr-20261020-01"])

    def test_waiting_approval_is_reminded_after_six_hours_once(self):
        vid = self.ready()
        poller = self.app.state.telegram_poller
        self.clock.advance(hours=6, minutes=1)

        poller.remind_due()
        poller.remind_due()

        reminders = [m for m in self.tg.sent("sendMessage") if "다시 알림" in m["text"]]
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"], f"ua:{vid}")


class OtherChatTest(AsmrCase):
    def test_other_chat_button_is_ignored(self):
        self.put("20261020-01_젤리.mp4")
        self.scan()
        self.tg.press("ua:asmr-20261020-01", chat="999")

        self.poll()

        self.assertEqual(self.video("asmr-20261020-01")["status"], "WAITING_UPLOAD")


class RealProbeTest(unittest.TestCase):
    def test_probe_reads_size_duration_and_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "v.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=108x192:d=1",
                            "-f", "lavfi", "-i", "sine=d=1", "-shortest", "-pix_fmt", "yuv420p", str(path)], check=True)

            p = probe_video(path)

        self.assertEqual((p["width"], p["height"], p["audio"]), (108, 192, True))
        self.assertAlmostEqual(p["durationSec"], 1.0, delta=0.1)


if __name__ == "__main__":
    unittest.main()
