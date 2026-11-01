"""목록형 최신 검색·반복 막기 (목록형쇼츠 v1.4 L23·L24, 2026-11-01 사용자: '최근 인기 스킬 5개' 가 매번 같은 내용).

- 주제에 '최근·최신·인기·요즘·트렌드' 가 있거나 /top …, 검색 이면 주제 단계가 사실 조사 요청(research, 중계기가 웹 검색을 켠다)으로
  후보·사실·출처를 받아 job.json 에 둔다. 대체 모델(로컬 LLM, 검색 없음)이 답하면 지어낸 출처일 수 있어 버리고 기록한다.
- 비슷한 주제의 이전 목록형 영상에서 다룬 항목을 대본 LLM 에 알리고, 1개 넘게 겹치면 한 번 더 묻는다(그래도 넘으면 기록).
"""
import json
import unittest

from app.llm.base import LlmResult
from app.pipeline.steps import listicle as ls
from tests.test_listicle import NAMES, ListicleCase, reply

RESEARCH = {"candidates": [{"name": n, "why": "요즘 많이 쓴다", "source": "https://github.com/x/" + n}
                           for n in ("frontend-design", "webapp-testing", "mcp-builder", "skill-creator")],
            "facts": ["frontend-design 은 화면 디자인을 다듬어 준다", "webapp-testing 은 Playwright 로 웹앱을 시험한다",
                      "mcp-builder 는 MCP 서버를 만드는 과정을 안내한다"],
            "sources": [{"title": "anthropics/skills", "url": "https://github.com/anthropics/skills"}]}


class ShouldResearchTest(unittest.TestCase):
    def test_keywords_or_flag(self):
        self.assertTrue(ls.should_research("최근 인기 많은 클로드 코드 스킬", None))
        self.assertTrue(ls.should_research("요즘 뜨는 터미널 도구", None))
        self.assertFalse(ls.should_research("깃 기본 명령어", None))
        self.assertTrue(ls.should_research("깃 기본 명령어", True))
        self.assertFalse(ls.should_research("최신 스킬", False))


class RepeatRuleTest(unittest.TestCase):
    def check(self, data, **kw):
        texts = [ls.split_emphasis(x)[0] for x in ls._flat_lines(data)]
        args = dict(n=3, given=[], max_sentence=28, target=sum(len("".join(t.split())) for t in texts), has_facts=False)
        args.update(kw)
        return ls.check_script(data, **args)

    def test_more_than_one_repeated_item_is_flagged_softly(self):
        problems = self.check(reply(), used=["Find-Skills", "superpowers", "pdf"])
        self.assertTrue([p for p in problems if p.startswith(ls.REPEAT_TAG)])

    def test_one_repeat_is_fine(self):
        self.assertEqual(self.check(reply(), used=["find-skills", "pdf"]), [])

    def test_operator_given_items_are_not_checked(self):
        self.assertEqual(self.check(reply(), used=NAMES, given=NAMES), [])


class ResearchFlowTest(ListicleCase):
    def previous(self, topic, names):
        job_id = self.post("/listicle", {"topic": topic, "count": len(names)}).json()["id"]
        d = self.job_dir(job_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "script.json").write_text(json.dumps({"listicle": {"items": [{"name": n} for n in names]}}, ensure_ascii=False),
                                       encoding="utf-8")
        return job_id

    def test_used_items_come_from_similar_topics_only(self):
        self.previous("클로드 코드 외부 스킬 추천", ["pdf", "docx", "xlsx"])
        self.previous("깃 명령어", ["git rebase", "git stash", "git bisect"])
        job_id = self.post("/listicle", {"topic": "최근 인기 클로드 코드 스킬", "count": 3}).json()["id"]
        self.llm.responses = [RESEARCH, reply()]
        self.run_step(job_id, "topic")
        self.run_step(job_id, "script")
        research = [r for r in self.llm.requests if r["schema_name"] == "research"][0]["messages"][-1]["content"]
        script = [r for r in self.llm.requests if r["schema_name"] == "listicle_script"][0]["messages"][-1]["content"]
        for text in (research, script):
            self.assertIn("pdf", text)
            self.assertIn("docx", text)
            self.assertNotIn("git rebase", text)

    def test_research_goes_into_job_json_and_script_prompt(self):
        job_id = self.post("/listicle", {"topic": "최근 인기 많은 클로드 코드 스킬", "count": 3}).json()["id"]
        self.llm.responses = [RESEARCH, reply()]
        self.run_step(job_id, "topic")
        self.assertEqual(self.get(f"/jobs/{job_id}/steps/topic").json()["status"], "succeeded")

        lst = self.read(job_id, "job.json")["listicle"]
        self.assertTrue(lst["research"])
        self.assertEqual([c["name"] for c in lst["candidates"]][:2], ["frontend-design", "webapp-testing"])
        self.assertIn("webapp-testing 은 Playwright 로 웹앱을 시험한다", lst["facts"])
        self.assertEqual(lst["sources"][0]["url"], "https://github.com/anthropics/skills")
        req = self.llm.requests[0]
        self.assertEqual(req["schema_name"], "research")
        self.assertIn("2026", req["messages"][-1]["content"])  # 오늘 날짜 기준으로 찾게

        self.run_step(job_id, "script")
        script = [r for r in self.llm.requests if r["schema_name"] == "listicle_script"][0]["messages"][-1]["content"]
        self.assertIn("mcp-builder", script)

    def test_no_research_without_keyword_or_flag(self):
        job_id = self.post("/listicle", {"topic": "깃 기본 명령어", "count": 3}).json()["id"]
        self.run_step(job_id, "topic")
        self.assertEqual(self.llm.requests, [])
        self.assertFalse(self.read(job_id, "job.json")["listicle"]["research"])

    def test_api_flag_turns_research_on(self):
        job_id = self.post("/listicle", {"topic": "깃 기본 명령어", "count": 3, "research": True}).json()["id"]
        self.llm.responses = [RESEARCH]
        self.run_step(job_id, "topic")
        self.assertEqual(self.llm.requests[0]["schema_name"], "research")

    def test_fallback_model_answer_is_dropped(self):
        job_id = self.post("/listicle", {"topic": "최신 클로드 스킬", "count": 3}).json()["id"]
        real = self.llm.generate_json

        def fallback(messages, schema, schema_name):
            r = real(messages, schema, schema_name)
            return LlmResult(data=r.data, model="fallback:qwen/qwen3.8-27b", input_tokens=1, output_tokens=1, source="content", raw=r.raw)
        self.llm.generate_json = fallback
        self.llm.responses = [RESEARCH]
        self.run_step(job_id, "topic")

        st = self.get(f"/jobs/{job_id}/steps/topic").json()
        self.assertEqual(st["status"], "succeeded")
        lst = self.read(job_id, "job.json")["listicle"]
        self.assertEqual((lst["candidates"], lst["facts"]), ([], []))
        self.assertIn("검색", json.dumps(st, ensure_ascii=False))

    def test_research_failure_does_not_stop_the_video(self):
        from app.llm.base import LlmError
        job_id = self.post("/listicle", {"topic": "최신 클로드 스킬", "count": 3}).json()["id"]
        self.llm.responses = [LlmError("transient", "timeout")] * 3
        self.run_step(job_id, "topic")
        self.assertEqual(self.get(f"/jobs/{job_id}/steps/topic").json()["status"], "succeeded")
        self.assertEqual(self.read(job_id, "job.json")["listicle"]["candidates"], [])


class TopSearchOptionTest(ListicleCase):
    def stored(self):
        from app.db.models import Job
        job_id = self.get("/jobs?status=PENDING").json()["items"][0]["id"]
        with self.app.state.db() as s:
            return s.get(Job, job_id).input["listicle"], s.get(Job, job_id).topic

    def test_search_word_and_theme_are_both_options(self):
        self.top("/top 클로드 코드 스킬, 3, 검색, paper")
        lst, topic = self.stored()
        self.assertEqual((topic, lst["research"], lst["theme"]), ("클로드 코드 스킬", True, "paper"))
        done = [m["text"] for m in self.tg.sent("sendMessage") if "등록" in m["text"]][0]
        self.assertIn("최신 검색", done)

    def test_keyword_turns_search_on(self):
        self.top("/top 요즘 인기 터미널 도구, 3")
        self.assertTrue(self.stored()[0]["research"])

    def test_plain_topic_has_no_search(self):
        self.top("/top 깃 기본 명령어, 3")
        self.assertFalse(self.stored()[0]["research"])


if __name__ == "__main__":
    unittest.main()
