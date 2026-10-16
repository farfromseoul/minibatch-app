"""ffprobe·ffmpeg 측정 (qc 단계의 재료). ffmpeg 가 있는 곳(job-api 이미지)에서만 돈다.

시험 영상은 ffmpeg 가 그 자리에서 만든다: 4초, 1080×1920 30fps, 앞 1초 소리 → 2.5초 무음 → 0.5초 소리.
"""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from app.media.ffmpeg import analyze, normalize_loudness, parse_ebur128, parse_loudnorm, parse_silences

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

    def test_loudnorm_json_from_stderr(self):
        log = ("[Parsed_loudnorm_0 @ 0x1] \n{\n\t\"input_i\" : \"-25.55\",\n\t\"input_tp\" : \"-10.45\",\n"
               "\t\"input_lra\" : \"5.10\",\n\t\"input_thresh\" : \"-35.93\",\n\t\"normalization_type\" : \"dynamic\",\n"
               "\t\"target_offset\" : \"0.13\"\n}\n")
        m = parse_loudnorm(log)
        self.assertEqual((m["input_i"], m["input_tp"], m["target_offset"]), ("-25.55", "-10.45", "0.13"))

    def test_loudnorm_missing(self):
        with self.assertRaises(ValueError):
            parse_loudnorm("출력 없음")


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

    def test_normalize_raises_quiet_audio_to_target_and_keeps_video(self):
        # 2026-10-16 실제 영상은 -25 LUFS 였다. 같은 정도로 작은 소리를 -14 로 맞춘다
        quiet = pathlib.Path(self._tmp.name) / "quiet.mp4"
        out = pathlib.Path(self._tmp.name) / "out.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(self.video), "-map", "0", "-c:v", "copy",
                        "-af", "volume=-20dB", "-c:a", "aac", str(quiet)], check=True)
        before = analyze(quiet)

        result = normalize_loudness(quiet, out, target_i=-14.0, true_peak=-1.5)

        after = analyze(out)
        self.assertLess(before["integratedLufs"], -25)
        self.assertAlmostEqual(after["integratedLufs"], -14.0, delta=1.0)
        self.assertEqual(after["video"]["frames"], before["video"]["frames"])  # 영상은 다시 인코딩하지 않는다
        self.assertEqual([s["codec"] for s in after["audio"]], ["aac"])
        self.assertAlmostEqual(float(result["input_i"]), before["integratedLufs"], delta=0.5)


if __name__ == "__main__":
    unittest.main()
