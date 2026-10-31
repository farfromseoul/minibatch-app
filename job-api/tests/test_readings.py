"""영어 읽기 (2026-10-31 사용자: 영어가 너무 빠르고 어색하게 읽힌다).

대본 LLM 이 대본 속 영어(로마자) 단어마다 한글 읽기를 함께 낸다(readings). TTS 는 공통 발음 사전과 합쳐 읽는 말로 바꾸고
(같은 단어는 공통 사전이 이긴다), 자막은 영어 그대로 둔다. 읽기가 빠지면 대본을 다시 요청하고, 끝까지 빠지면 기록만 남긴다.
"""
import json
import pathlib
import shutil
import unittest

from app.text import readings as rd
from tests.fakes import FakeLlm, FakeRegistry, script_of
from tests.test_media_steps import FakeWorker, MediaCase

REAL = pathlib.Path(__file__).resolve().parents[1] / "content"


class ReadingRulesTest(unittest.TestCase):
    def test_valid_items_become_map(self):
        m, problems = rd.to_map([{"term": "docx", "reading": "독스"}, {"term": "Claude Code", "reading": "클로드 코드"}],
                                ["둘째, 워드 만드는 docx예요.", "Claude Code 로 써요."])
        self.assertEqual(m, {"docx": "독스", "Claude Code": "클로드 코드"})
        self.assertEqual(problems, [])

    def test_reading_must_be_hangul_and_term_in_script(self):
        m, problems = rd.to_map([{"term": "pdf", "reading": "pdf"}, {"term": "xlsx", "reading": "엑셀"}], ["첫째는 pdf예요."])
        self.assertEqual(m, {})
        self.assertTrue(any("한글" in p for p in problems))
        self.assertTrue(any("xlsx" in p for p in problems))

    def test_missing_lists_latin_words_left_after_readings_and_dictionary(self):
        sentences = ["첫째는 pdf예요.", "AI 가 skill-creator 로 만들어요.", "GPU 3개"]
        left = rd.missing(sentences, {"pdf": "피디에프", "AI": "에이아이", "GPU": "지피유"})
        self.assertEqual(left, ["skill-creator"])

    def test_merge_keeps_dictionary_over_llm(self):
        words = rd.merge({"AI": "에이 아이", "docx": "독스"}, {"AI": "에이아이"})
        self.assertEqual(words, {"AI": "에이아이", "docx": "독스"})


class ScriptReadingsTest(MediaCase):
    pipeline = ["topic", "script", "review", "scenes", "tts"]

    def setUp(self):
        self.llm = FakeLlm()
        super().setUp()

    def make_providers(self):
        return FakeRegistry(self.llm, tts_url=self.url)

    def make_steps(self):
        return {}  # 진짜 단계

    def test_readings_reach_tts_and_captions_keep_english(self):
        from tests.fakes import GOOD_SCORES
        job_id = self.new_job("문서 스킬")
        data = script_of(30, 8)
        data["body"][0] = "둘째는 워드 파일을 만드는 docx 예요 가나다라."
        data["readings"] = [{"term": "docx", "reading": "독스"}]
        scenes = {"scenes": [{"role": "hook", "sentences": [1, 2], "component": "TitleReveal", "props": {"title": "x"}, "animationPreset": "pop"},
                             {"role": "explain", "sentences": [3, 4, 5], "component": "TitleReveal", "props": {"title": "y"}, "animationPreset": "fade"},
                             {"role": "summary", "sentences": [6, 7, 8], "component": "SummaryScene",
                              "props": {"points": ["정리"]}, "animationPreset": "fade"}]}
        # 글자 수가 목표와 달라 대본을 세 번 묻는다(글자 수만 어긋나면 통과)
        self.llm.responses = [data, data, data, {"issues": [], "scores": GOOD_SCORES, "verdict": "pass"}, scenes]
        for step in self.pipeline:
            self.assertIn(self.run_step(job_id, step).status_code, (200, 202), step)

        self.assertEqual(self.read(job_id, "script.json")["readings"], {"docx": "독스"})
        self.assertEqual(self.read(job_id, "scenes.json")["readings"], {"docx": "독스"})
        sent = [s["text"] for p, b in FakeWorker.received if p == "/synthesize" for s in b["sentences"]]
        self.assertIn("둘째는 워드 파일을 만드는 독스 예요 가나다라.", sent)
        tts = self.read(job_id, "tts.json")
        self.assertIn("둘째는 워드 파일을 만드는 docx 예요 가나다라.", [i["text"] for i in tts["items"]])  # 자막은 원문

    def test_missing_reading_is_asked_separately_not_by_rewriting_script(self):
        job_id = self.new_job("문서 스킬")
        data = script_of(30, 8)
        data["body"][0] = "둘째는 워드 파일을 만드는 docx 예요 가나다라."
        # 글자 수 때문에 대본은 세 번 묻고(기존 규칙), 읽기는 빠진 단어만 한 번 따로 묻는다
        self.llm.responses = [data, data, data, {"readings": [{"term": "docx", "reading": "독스"}]}]

        self.run_step(job_id, "topic")
        self.run_step(job_id, "script")

        names = [r["schema_name"] for r in self.llm.requests]
        self.assertEqual(names, ["script", "script", "script", "readings"])
        self.assertIn("- docx", self.llm.requests[-1]["messages"][-1]["content"])
        self.assertEqual(self.read(job_id, "script.json")["readings"], {"docx": "독스"})

    def test_reading_failure_only_noted(self):
        job_id = self.new_job("문서 스킬")
        data = script_of(30, 8)
        data["body"][0] = "둘째는 워드 파일을 만드는 docx 예요 가나다라."
        self.llm.responses = [data, data, data, {"readings": [{"term": "docx", "reading": "docx"}]}] + [{"readings": []}] * 2

        self.run_step(job_id, "topic")
        self.run_step(job_id, "script")

        st = self.get(f"/jobs/{job_id}/steps/script").json()
        self.assertEqual(st["status"], "succeeded")
        self.assertEqual(self.read(job_id, "script.json")["readings"], {})

    def test_prompt_asks_for_readings(self):
        job_id = self.new_job("문서 스킬")
        self.llm.responses = [script_of(30, 8)]
        self.run_step(job_id, "topic")
        self.run_step(job_id, "script")
        prompt = self.llm.requests[0]["messages"][-1]["content"]
        self.assertIn("readings", prompt)
        self.assertIn("readings", json.dumps(self.llm.requests[0]["schema"]))
