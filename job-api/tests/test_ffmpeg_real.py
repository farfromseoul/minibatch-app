"""ffprobe·ffmpeg 측정 (qc 단계의 재료). ffmpeg 가 있는 곳(job-api 이미지)에서만 돈다.

시험 영상은 ffmpeg 가 그 자리에서 만든다: 4초, 1080×1920 30fps, 앞 1초 소리 → 2.5초 무음 → 0.5초 소리.
"""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from app.media.ffmpeg import analyze, parse_ebur128, parse_silences

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


class ParseTest(unittest.TestCase):
    """ffmpeg 출력 해석. 2026-10-16 실제 영상(첫 영상·시리즈 1·2화)의 출력 모양 그대로"""

    def test_silences(self):
        log = ("[silencedetect @ 0x1] silence_start: 25.1883\n"
               "[silencedetect @ 0x1] silence_end: 26.8259 | silence_duration: 1.6376\n"
               "[silencedetect @ 0x1] silence_start: 61.9\n")
        self.assertEqual(parse_silences(log, end=62.5), [(25.1883, 26.8259), (61.9, 62.5)])  # 끝까지 무음이면 끝 시각으로 닫는다

    def test_integrated_loudness_from_summary(self):
        log = ("[Parsed_ebur128_0 @ 0x1] t: 1.0 TARGET:-23 LUFS M: -30.1 S:-120.7 I: -31.0 LUFS\n"
               "[Parsed_ebur128_0 @ 0x1] Summary:\n\n  Integrated loudness:\n    I:         -25.5 LUFS\n")
        self.assertEqual(parse_ebur128(log), -25.5)  # 진행 줄의 I: 가 아니라 요약의 값

    def test_missing_summary(self):
        self.assertIsNone(parse_ebur128("아무것도 없음"))


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg 없음 (job-api 이미지에서 확인)")
class AnalyzeRealTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.video = pathlib.Path(cls._tmp.name) / "t.mp4"
        audio = "sine=f=440:d=1[a];anullsrc=r=48000:cl=stereo:d=2.5[b];sine=f=440:d=0.5[c];[a][b][c]concat=n=3:v=0:a=1[out]"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=4",
                        "-filter_complex", audio, "-map", "0:v", "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-ac", "2", "-shortest", str(cls.video)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_measures_streams_loudness_and_silence(self):
        a = analyze(self.video, silence_db=-50, silence_min_sec=1.5)

        self.assertAlmostEqual(a["durationSec"], 4.0, delta=0.1)
        self.assertEqual((a["video"]["width"], a["video"]["height"], a["video"]["fps"]), (1080, 1920, 30.0))
        self.assertAlmostEqual(a["video"]["frames"], 120, delta=1)
        self.assertEqual([s["codec"] for s in a["audio"]], ["aac"])
        self.assertIsInstance(a["integratedLufs"], float)
        self.assertEqual(len(a["silences"]), 1)
        start, end = a["silences"][0]
        self.assertAlmostEqual(end - start, 2.5, delta=0.2)


if __name__ == "__main__":
    unittest.main()
