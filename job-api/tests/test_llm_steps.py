"""script·review·scenes 단계 (앱 설계 "LLM 사용", "길이 맞추기", D24 시리즈 입력).

가짜 LLM 이 미리 넣은 응답을 돌려준다. 카테고리 파일은 실제 content/categories/ai-it.yaml 을 쓴다.
"""
import json
import pathlib
import shutil

from app.llm.base import LlmError
from tests.fakes import FakeLlm, FakeRegistry, script_of, transient
from tests.helpers import AppTestCase

REAL_CATEGORY = pathlib.Path(__file__).resolve().parents[1] / "content" / "categories" / "ai-it.yaml"
TARGET = round(60 * 5.6 * 0.9)  # 302


class LlmStepCase(AppTestCase):
    pipeline = ["topic", "script", "review", "scenes"]

    def make_steps(self):
        return {}  # 진짜 단계를 쓴다

    def setUp(self):
        self.llm = FakeLlm()
        super().setUp()
        shutil.copy(REAL_CATEGORY, self.settings.content_dir / "categories" / "ai-it.yaml")

    def make_providers(self):
        return FakeRegistry(self.llm)

    def job_until(self, step, topic="RAG란?"):
        job_id = self.new_job(topic)
        self.run_until(job_id, step)
        return job_id

    def read(self, job_id, name):
        return json.loads((self.job_dir(job_id) / name).read_text())

    def status(self, job_id, step):
        return self.get(f"/jobs/{job_id}/steps/{step}").json()


class ScriptStepTest(LlmStepCase):
    def test_writes_script_with_meta_when_length_fits(self):
        self.llm.responses = [script_of(chars_per_sentence=38, sentences=8)]  # 304자

        job_id = self.job_until("script")

        s = self.read(job_id, "script.json")
        self.assertEqual(s["hook"][:4], "문장90")
        self.assertEqual(s["meta"]["targetChars"], TARGET)
        self.assertEqual(s["meta"]["attempts"], 1)
        self.assertEqual(s["meta"]["model"], "fake-model")
        self.assertTrue(s["meta"]["promptVersion"])

    def test_prompt_uses_category_and_target(self):
        self.llm.responses = [script_of(38, 8)]

        self.job_until("script")

        prompt = self.llm.requests[0]["messages"][-1]["content"]
        self.assertIn("RAG란?", prompt)
        self.assertIn("비전공 개발 입문자", prompt)  # 카테고리 audience
        self.assertIn(str(TARGET), prompt)
        self.assertIn("40자", prompt)

    def test_too_short_script_is_requested_again_longer(self):
        self.llm.responses = [script_of(15, 8), script_of(38, 8)]  # 120자 → 304자

        job_id = self.job_until("script")

        self.assertEqual(len(self.llm.requests), 2)
        self.assertIn("늘려", self.llm.last_user_text())
        self.assertEqual(self.read(job_id, "script.json")["meta"]["attempts"], 2)

    def test_long_script_is_trimmed_from_the_end_of_body(self):
        self.llm.responses = [script_of(38, 12)]  # 456자

        job_id = self.job_until("script")

        s = self.read(job_id, "script.json")
        self.assertLessEqual(s["meta"]["charCount"], round(TARGET * 1.04))
        self.assertEqual(len(self.llm.requests), 1)  # 다시 묻지 않고 코드가 맞춘다
        self.assertTrue(s["summary"].startswith("문장91"))  # 요약은 남는다
        self.assertEqual(len(s["meta"]["trimmedSentences"]), 4)

    def test_still_off_length_after_retries_is_degraded_not_failed(self):
        self.llm.responses = [script_of(15, 8)] * 3

        job_id = self.job_until("script")

        st = self.status(job_id, "script")
        self.assertEqual((st["status"], st["kind"]), ("succeeded", "degraded"))
        self.assertIn("글자 수", st["error"])

    def test_long_sentence_is_fixed_or_fails_deterministically(self):
        self.llm.responses = [script_of(45, 7)] * 3  # 문장마다 45자 > 40

        job_id = self.new_job()
        self.run_step(job_id, "topic")
        self.run_step(job_id, "script")

        st = self.status(job_id, "script")
        self.assertEqual((st["status"], st["kind"], st["retryFrom"]), ("failed", "deterministic", "script"))
        self.assertIn("40자", self.llm.last_user_text())

    def test_llm_down_is_transient(self):
        self.llm.responses = [transient()]

        job_id = self.new_job()
        self.run_step(job_id, "topic")
        self.run_step(job_id, "script")

        self.assertEqual(self.status(job_id, "script")["kind"], "transient")

    def test_invalid_output_is_retried(self):
        self.llm.responses = [LlmError("invalid_output", "JSON 아님"), script_of(38, 8)]

        job_id = self.job_until("script")

        self.assertEqual(self.read(job_id, "script.json")["meta"]["attempts"], 2)


class SeriesScriptTest(LlmStepCase):
    SERIES = {"key": "ai-office", "title": "민지의 AI 적응기", "bible": {"premise": "민지가 매화 배운다"},
              "episodes": [{"number": 1, "title": "AI가 뭐길래", "outline": "AI의 뜻"},
                           {"number": 2, "title": "머신러닝", "outline": "데이터로 배운다"}]}

    def episode2_job(self):
        self.post("/series", self.SERIES)
        job1 = self.post("/jobs", {"seriesId": "ai-office"}).json()["id"]
        self.llm.responses = [script_of(38, 8, episodeSummary="민지가 AI 뜻을 배움", nextTeaser="다음엔 머신러닝")]
        self.run_until(job1, "script")
        # 1화 검토·장면은 생략: 작업을 REVIEW 로 만들어 승인한다
        from app.db.models import Job
        with self.app.state.db() as s:
            s.get(Job, job1).status = "REVIEW"
            s.commit()
        self.post(f"/jobs/{job1}/approve", {"approvedBy": "운영자"})
        return self.post("/jobs", {"seriesId": "ai-office"}).json()["id"]

    def test_episode2_prompt_has_story_so_far_and_requires_recap(self):
        job2 = self.episode2_job()
        self.llm.responses = [script_of(38, 8), script_of(38, 8, recap="지난 이야기: 민지는 AI 뜻을 배웠다.",
                                                         episodeSummary="머신러닝을 배움")]

        self.run_until(job2, "script")

        first_prompt = self.llm.requests[-2]["messages"][-1]["content"]
        self.assertIn("민지가 AI 뜻을 배움", first_prompt)  # 1화 요약
        self.assertIn("데이터로 배운다", first_prompt)  # 이번 화 계획
        self.assertIn("recap", self.llm.last_user_text())  # 첫 응답에 recap 이 없어 다시 요청
        self.assertTrue(self.read(job2, "script.json")["recap"].startswith("지난 이야기"))


class ReviewStepTest(LlmStepCase):
    def test_pass_with_rule_warnings(self):
        script = script_of(38, 8)
        script["body"][0] = "2017년에 나온 기술은 100% 정확합니다 가가가가가가가가가가가가가가."
        self.llm.responses = [script, {"issues": [{"line": 2, "severity": "warning", "reason": "모호"}], "verdict": "pass"}]

        job_id = self.job_until("review")

        r = self.read(job_id, "review.json")
        kinds = {w["rule"] for w in r["ruleWarnings"]}
        self.assertTrue({"banned_word", "number"} <= kinds)
        self.assertEqual(r["verdict"], "pass")

    def test_critical_issue_fails_with_retry_from_script(self):
        self.llm.responses = [script_of(38, 8), {"issues": [{"line": 3, "severity": "critical", "reason": "RAG를 학습 방식으로 설명"}], "verdict": "fail"}]

        job_id = self.new_job()
        for step in ("topic", "script", "review"):
            self.run_step(job_id, step)

        st = self.status(job_id, "review")
        self.assertEqual((st["kind"], st["retryFrom"]), ("deterministic", "script"))
        self.assertIn("학습 방식", st["error"])


class ScenesStepTest(LlmStepCase):
    def sentences(self, script):
        return [script["hook"], *script["body"], script["summary"]]

    def good_scenes(self, script):
        return {"scenes": [
            {"role": "hook", "sentences": [1], "component": "TitleReveal", "props": {"title": "RAG", "subtitle": "검색 증강 생성"}, "animationPreset": "pop"},
            {"role": "explain", "sentences": [2, 3, 4], "component": "FlowDiagram",
             "props": {"nodes": [{"id": "q", "label": "질문"}, {"id": "l", "label": "LLM"}], "edges": [["q", "l"]], "revealOrder": ["q", "l"]},
             "animationPreset": "sequential"},
            {"role": "explain", "sentences": [5, 6, 7], "component": "ComparisonCards",
             "props": {"left": {"title": "LLM", "points": ["기억"]}, "right": {"title": "RAG", "points": ["검색"]}}, "animationPreset": "fade"},
            {"role": "summary", "sentences": [8], "component": "SummaryScene", "props": {"points": ["찾고", "넘긴다"]}, "animationPreset": "fade"},
        ]}

    def test_writes_scenes_json(self):
        script = script_of(38, 8)
        self.llm.responses = [script, {"issues": [], "verdict": "pass"}, self.good_scenes(script)]

        job_id = self.job_until("scenes")

        sc = self.read(job_id, "scenes.json")
        self.assertEqual([s["id"] for s in sc["scenes"]], ["s01", "s02", "s03", "s04"])
        self.assertEqual(sc["scenes"][1]["lines"], self.sentences(script)[1:4])  # 번호로 문장을 채운다
        self.assertEqual(sc["scenes"][1]["visual"], {"type": "template", "component": "FlowDiagram",
                                                    "props": self.good_scenes(script)["scenes"][1]["props"]})
        self.assertEqual(sc["title"], "제목 하나")
        prompt = self.llm.requests[-1]["messages"][-1]["content"]
        self.assertIn("FlowDiagram", prompt)  # 카테고리 템플릿 목록이 프롬프트에 들어간다

    def test_lines_must_match_script_in_order_then_retry(self):
        script = script_of(38, 8)
        bad = self.good_scenes(script)
        bad["scenes"][1]["sentences"] = [4, 3, 2]
        self.llm.responses = [script, {"issues": [], "verdict": "pass"}, bad, self.good_scenes(script)]

        job_id = self.job_until("scenes")

        self.assertIn("차례대로", self.llm.last_user_text())
        self.assertTrue((self.job_dir(job_id) / "scenes.json").is_file())

    def test_same_template_three_times_in_a_row_is_retried(self):
        script = script_of(38, 8)
        bad = self.good_scenes(script)
        flow = bad["scenes"][1]
        bad["scenes"][2] = dict(flow, sentences=[5, 6])
        bad["scenes"].insert(3, dict(flow, sentences=[7]))
        self.llm.responses = [script, {"issues": [], "verdict": "pass"}, bad, self.good_scenes(script)]

        self.job_until("scenes")

        self.assertIn("세 번 연달아", self.llm.last_user_text())

    def test_bad_props_three_times_fails_deterministically(self):
        script = script_of(38, 8)
        bad = self.good_scenes(script)
        bad["scenes"][1]["props"]["edges"] = [["q", "없는노드"]]
        self.llm.responses = [script, {"issues": [], "verdict": "pass"}, bad, bad, bad]

        job_id = self.new_job()
        for step in ("topic", "script", "review", "scenes"):
            self.run_step(job_id, step)

        st = self.status(job_id, "scenes")
        self.assertEqual((st["kind"], st["retryFrom"]), ("deterministic", "scenes"))
        self.assertIn("없는노드", st["error"])
