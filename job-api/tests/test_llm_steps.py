"""script·review·scenes 단계 (앱 설계 "LLM 사용", "길이 맞추기", D24 시리즈 입력).

가짜 LLM 이 미리 넣은 응답을 돌려준다. 카테고리 파일은 실제 content/categories/ai-it.yaml 을 쓴다.
"""
import json
import pathlib
import shutil

from app.llm.base import LlmError
from tests.fakes import GOOD_SCORES, FakeLlm, FakeRegistry, script_of, transient
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

        prompt = "\n".join(m["content"] for m in self.llm.requests[0]["messages"])  # system(규칙) + user(주제·분량)
        self.assertIn("RAG란?", prompt)
        self.assertIn("원리는 모르는 직장인·학생", prompt)  # 카테고리 audience
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

    def test_trim_never_goes_below_the_lower_bound(self):
        # 후킹·요약 40자, 설명 39자 × 7 = 353자. 한 문장 빼면 314(+4% 안), 두 문장 빼면 275(하한 281 미만)
        self.llm.responses = [script_of(39, 9)]

        job_id = self.job_until("script")

        s = self.read(job_id, "script.json")
        self.assertEqual(s["meta"]["charCount"], 314)
        self.assertEqual(len(s["meta"]["trimmedSentences"]), 1)
        self.assertEqual(len(self.llm.requests), 1)

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

    def test_last_episode_prompt_asks_to_wrap_up_the_series(self):
        job2 = self.episode2_job()  # 2화가 마지막 화
        self.llm.responses = [script_of(38, 8, recap="지난 화에서 AI 뜻을 봤죠.", episodeSummary="머신러닝을 배움")]

        self.run_until(job2, "script")

        prompt = self.llm.last_user_text()
        self.assertIn("마지막 화", prompt)
        self.assertIn("시리즈 전체", prompt)  # summary 로 시리즈를 마무리한다 (D33, 2026-10-18 사용자 요청)


class ReviewStepTest(LlmStepCase):
    def test_pass_with_rule_warnings(self):
        script = script_of(38, 8)
        script["body"][0] = "2017년에 나온 기술은 100% 정확합니다 가가가가가가가가가가가가가가."
        self.llm.responses = [script, {"issues": [{"line": 2, "severity": "warning", "reason": "모호"}], "scores": GOOD_SCORES, "verdict": "pass"}]

        job_id = self.job_until("review")

        r = self.read(job_id, "review.json")
        kinds = {w["rule"] for w in r["ruleWarnings"]}
        self.assertTrue({"banned_word", "number"} <= kinds)
        self.assertEqual(r["verdict"], "pass")

    def test_critical_issue_fails_with_retry_from_script(self):
        self.llm.responses = [script_of(38, 8), {"issues": [{"line": 3, "severity": "critical", "reason": "RAG를 학습 방식으로 설명"}], "scores": GOOD_SCORES, "verdict": "fail"}]

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
        self.llm.responses = [script, {"issues": [], "scores": GOOD_SCORES, "verdict": "pass"}, self.good_scenes(script)]

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
        self.llm.responses = [script, {"issues": [], "scores": GOOD_SCORES, "verdict": "pass"}, bad, self.good_scenes(script)]

        job_id = self.job_until("scenes")

        self.assertIn("차례대로", self.llm.last_user_text())
        self.assertTrue((self.job_dir(job_id) / "scenes.json").is_file())

    def test_same_template_three_times_in_a_row_is_retried(self):
        script = script_of(38, 8)
        bad = self.good_scenes(script)
        flow = bad["scenes"][1]
        bad["scenes"][2] = dict(flow, sentences=[5, 6])
        bad["scenes"].insert(3, dict(flow, sentences=[7]))
        self.llm.responses = [script, {"issues": [], "scores": GOOD_SCORES, "verdict": "pass"}, bad, self.good_scenes(script)]

        self.job_until("scenes")

        self.assertIn("세 번 연달아", self.llm.last_user_text())

    def test_bad_props_three_times_fails_deterministically(self):
        script = script_of(38, 8)
        bad = self.good_scenes(script)
        bad["scenes"][1]["props"]["edges"] = [["q", "없는노드"]]
        self.llm.responses = [script, {"issues": [], "scores": GOOD_SCORES, "verdict": "pass"}, bad, bad, bad]

        job_id = self.new_job()
        for step in ("topic", "script", "review", "scenes"):
            self.run_step(job_id, step)

        st = self.status(job_id, "scenes")
        self.assertEqual((st["kind"], st["retryFrom"]), ("deterministic", "scenes"))
        self.assertIn("없는노드", st["error"])


class SeriesOutroTest(LlmStepCase):
    """시리즈 연결 ① (D26): 영상 끝 안내 문구와 다음 화 화면은 코드가 붙인다. 문구는 카테고리 파일"""

    PLAN = {"key": "ai-office", "title": "민지의 AI 적응기", "bible": {"premise": "민지가 매화 배운다"},
            "episodes": [{"number": 1, "title": "AI가 뭐길래", "outline": "AI의 뜻"},
                         {"number": 2, "title": "머신러닝은 뭐가 달라", "outline": "데이터로 배운다"}]}

    def setUp(self):
        super().setUp()
        cat = self.settings.content_dir / "categories" / "ai-it.yaml"
        cat.write_text(cat.read_text(encoding="utf-8").split("\nseries:")[0] + """
series:
  cta_next:
    - "다음 이야기가 궁금하면 이어지는 영상으로!"
    - "{next_title}, 다음 화에서 만나요!"
  cta_end:
    - "{series_title} 끝까지 봐 줘서 고마워요!"
""", encoding="utf-8")

    def scenes_for(self, script):
        n = len([script.get("recap"), script["hook"], *script["body"], script["summary"], script.get("nextTeaser")]) - \
            (0 if script.get("recap") else 1) - (0 if script.get("nextTeaser") else 1)
        return {"scenes": [
            {"role": "hook", "sentences": [1], "component": "TitleReveal", "props": {"title": "AI"}, "animationPreset": "pop"},
            {"role": "summary", "sentences": list(range(2, n + 1))[:4] if n <= 5 else list(range(2, 6)), "component": "SummaryScene",
             "props": {"points": ["정리"]}, "animationPreset": "fade"},
        ] + ([{"role": "summary", "sentences": list(range(6, n + 1)), "component": "SummaryScene",
               "props": {"points": ["끝"]}, "animationPreset": "fade"}] if n > 5 else [])}

    def ep1(self):
        self.post("/series", self.PLAN)
        job = self.post("/jobs", {"seriesId": "ai-office"}).json()["id"]
        script = script_of(33, 8, episodeSummary="민지가 AI 뜻을 배움", nextTeaser="다음엔 데이터로 배우는 법!")  # 264+예고 12 = 276자: 끝 문장 몫을 뺀 목표 안
        self.llm.responses = [script, {"issues": [], "scores": GOOD_SCORES, "verdict": "pass"}, self.scenes_for(script)]
        self.run_until(job, "scenes")
        return job

    def test_episode_with_next_gets_outro_scene_from_category(self):
        job = self.ep1()

        sc = self.read(job, "scenes.json")["scenes"]
        last = sc[-1]
        self.assertEqual(last["role"], "outro")
        self.assertEqual(last["lines"], ["다음 이야기가 궁금하면 이어지는 영상으로!"])  # 1화 → 목록 첫 번째
        self.assertEqual(last["visual"]["component"], "TitleReveal")
        self.assertEqual(last["visual"]["props"], {"title": "다음 화", "subtitle": "머신러닝은 뭐가 달라"})
        self.assertNotIn("이어지는 영상", self.llm.requests[2]["messages"][-1]["content"])  # LLM 에는 안 보낸다

    def test_target_chars_leave_room_for_the_outro(self):
        self.ep1()

        prompt = self.llm.requests[0]["messages"][-1]["content"]
        cta = len("다음이야기가궁금하면이어지는영상으로!")
        expected = round(60 * 5.6 * 0.9) - cta - round(0.5 * 5.6)
        self.assertIn(f"{expected}자", prompt)

    def test_last_episode_gets_ending_line_with_series_title(self):
        job1 = self.ep1()
        from app.db.models import Job
        with self.app.state.db() as s:
            s.get(Job, job1).status = "REVIEW"
            s.commit()
        self.post(f"/jobs/{job1}/approve", {"approvedBy": "운영자"})
        job2 = self.post("/jobs", {"seriesId": "ai-office"}).json()["id"]
        script = script_of(33, 8, recap="지난 이야기: 민지는 AI 뜻을 배웠다.", episodeSummary="머신러닝을 배움")
        self.llm.responses = [script, {"issues": [], "scores": GOOD_SCORES, "verdict": "pass"}, self.scenes_for(script)]

        self.run_until(job2, "scenes")

        last = self.read(job2, "scenes.json")["scenes"][-1]
        self.assertEqual(last["lines"], ["민지의 AI 적응기 끝까지 봐 줘서 고마워요!"])
        self.assertEqual(last["visual"]["props"], {"title": "끝", "subtitle": "민지의 AI 적응기"})

    def test_standalone_video_has_no_outro(self):
        script = script_of(38, 8)
        self.llm.responses = [script, {"issues": [], "scores": GOOD_SCORES, "verdict": "pass"}, self.scenes_for(script)]

        job = self.job_until("scenes")

        self.assertNotEqual(self.read(job, "scenes.json")["scenes"][-1]["role"], "outro")
