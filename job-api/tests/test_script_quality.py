"""대본 품질 개선 (2026-10-17 사용자 요청: 가상 인물·판타지가 오글거리고 내용이 어렵다).

- 프롬프트를 system(역할·구조·금지 규칙)과 user(이번 주제·분량)로 나눈다
- 시리즈는 가상 인물 없이 진행자 한 명이 이어서 설명하는 연속 강의형
- 문장 길이를 자연스럽게(문장당 기준 글자를 늘림)
- 검토는 정확성·이해 쉬움·구체성·자연스러움을 1~5점으로 매기고 2점 이하가 있으면 대본부터 다시
"""
import json
import pathlib
import shutil

import yaml

from app.pipeline.steps import script as script_mod
from tests.fakes import FakeLlm, FakeRegistry, script_of
from tests.helpers import AppTestCase

REAL_CATEGORY = pathlib.Path(__file__).resolve().parents[1] / "content" / "categories" / "ai-it.yaml"
SCORES = {"accuracy": 5, "clarity": 4, "concreteness": 4, "naturalness": 4}


class QualityCase(AppTestCase):
    pipeline = ["topic", "script", "review"]

    def make_steps(self):
        return {}

    def setUp(self):
        self.llm = FakeLlm()
        super().setUp()
        shutil.copy(REAL_CATEGORY, self.settings.content_dir / "categories" / "ai-it.yaml")

    def make_providers(self):
        return FakeRegistry(self.llm, chars_per_sec=5.0)

    def status(self, job_id, step):
        return self.get(f"/jobs/{job_id}/steps/{step}").json()


class CategoryTest(QualityCase):
    def test_category_asks_for_concrete_structure_and_bans_characters(self):
        cat = yaml.safe_load(REAL_CATEGORY.read_text(encoding="utf-8"))
        forbidden = " ".join(cat["script"]["forbidden"])
        self.assertIn("실제 서비스", cat["script"]["structure"])
        self.assertIn("정의", cat["script"]["structure"])
        for word in ("가상 인물", "지문", "비유"):
            self.assertIn(word, forbidden)
        self.assertIn("이해", " ".join(cat["review"]["rules"]))


class ScriptPromptTest(QualityCase):
    def test_rules_go_to_system_and_topic_to_user(self):
        self.llm.responses = [script_of(30, 10)]
        job_id = self.new_job("AI는 어떻게 이미지를 만들까?")

        self.run_until(job_id, "script")

        system, user = self.llm.requests[0]["messages"][:2]
        self.assertEqual((system["role"], user["role"]), ("system", "user"))
        self.assertIn("가상 인물", system["content"])
        self.assertIn("진행자", system["content"])
        self.assertIn("비유는 최대 하나", system["content"])
        self.assertIn("AI는 어떻게 이미지를 만들까?", user["content"])
        self.assertNotIn("가상 인물", user["content"])

    def test_sentences_are_planned_at_natural_length(self):
        self.assertGreaterEqual(script_mod.CHARS_PER_SENTENCE, 22)  # 17자 기준이 문장을 뚝뚝 끊었다
        total, min_chars = script_mod.sentence_plan(270, 40)
        self.assertLessEqual(total, 12)
        self.assertGreaterEqual(min_chars, 15)


class SeriesLectureTest(QualityCase):
    def test_series_block_is_lecture_not_drama(self):
        self.post("/series", {"key": "s1", "category": "ai-it", "title": "AI가 말을 이해하는 법",
                              "bible": {"premise": "AI 언어 모델의 원리를 차례로", "tone": "차분한 설명"},
                              "episodes": [{"number": 1, "title": "토큰이란?", "outline": "문장을 조각으로"},
                                           {"number": 2, "title": "임베딩이란?", "outline": "조각을 숫자로"}]})
        job_id = self.post("/jobs", {"seriesId": "s1"}).json()["id"]
        self.llm.responses = [script_of(30, 9, episodeSummary="토큰을 배웠다", nextTeaser="그 조각은 어떻게 숫자가 될까?")]

        self.run_until(job_id, "script")

        user = self.llm.requests[0]["messages"][-1]["content"]
        self.assertIn("연속 강의", user)
        self.assertNotIn("드라마", user)
        self.assertNotIn("줄거리", user)


PLAN = {"title": "AI가 말을 이해하는 법", "bible": {"premise": "언어 모델의 원리를 쉬운 것부터", "tone": "차분한 설명"},
        "episodes": [{"title": "토큰이란?", "outline": "a"}, {"title": "임베딩이란?", "outline": "b"}]}


class SeriesPlanTest(QualityCase):
    def test_plan_has_no_characters_and_forbids_fiction(self):
        self.llm.responses = [PLAN]

        res = self.post("/series", {"category": "ai-it", "episodeCount": 2})

        self.assertEqual(res.status_code, 201, res.text)
        req = self.llm.requests[0]
        bible = req["schema"]["properties"]["bible"]
        self.assertNotIn("characters", bible["properties"])
        self.assertEqual(req["messages"][0]["role"], "system")
        self.assertIn("가상 인물", req["messages"][0]["content"])


class ReviewScoreTest(QualityCase):
    def run_review(self, review):
        self.llm.responses = [script_of(30, 10), review]
        job_id = self.new_job()
        for step in ("topic", "script", "review"):
            self.run_step(job_id, step)
        return job_id

    def test_scores_are_required_and_recorded(self):
        job_id = self.run_review({"issues": [], "scores": SCORES, "verdict": "pass"})

        self.assertEqual(self.status(job_id, "review")["status"], "succeeded")
        r = json.loads((self.job_dir(job_id) / "review.json").read_text())
        self.assertEqual(r["scores"], SCORES)
        system = self.llm.requests[1]["messages"][0]
        self.assertEqual(system["role"], "system")
        self.assertIn("이해", system["content"])
        self.assertEqual(set(self.llm.requests[1]["schema"]["properties"]["scores"]["required"]),
                         {"accuracy", "clarity", "concreteness", "naturalness"})

    def test_low_score_sends_back_to_script(self):
        job_id = self.run_review({"issues": [{"line": 3, "severity": "warning", "reason": "가상 인물 대사"}],
                                  "scores": dict(SCORES, naturalness=2), "verdict": "pass"})

        st = self.status(job_id, "review")
        self.assertEqual((st["kind"], st["retryFrom"]), ("deterministic", "script"))
        self.assertIn("자연스러움 2점", st["error"])
