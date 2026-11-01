"""목록형 개수 1~10과 길이 (목록형쇼츠 v1.4 L26, 2026-11-01 사용자: 3~5개 제약이 아쉽다. 1~10개, 길이는 개수에 따라).

목표 길이 = duration.base + duration.per_item × N (카테고리 설정). 항목이 7개 이상이면 항목 문장을 3 → 2로 줄인다.
"""
import unittest

from app.notify.approvals import parse_request
from app.pipeline.steps import listicle as ls
from app.schemas.templates import check_props
from tests.test_listicle import ListicleCase, reply

NAMES10 = [f"tool-{i}" for i in range(1, 11)]


class CountRulesTest(unittest.TestCase):
    def test_item_lines_shrink_for_many_items(self):
        self.assertEqual([ls.item_lines(n) for n in (1, 5, 6, 7, 10)], [3, 3, 3, 2, 2])
        lines = ls._schema(8)["properties"]["items"]["items"]["properties"]["lines"]
        self.assertEqual((lines["minItems"], lines["maxItems"]), (2, 3))

    def test_target_chars_grow_with_count(self):
        self.assertGreater(ls.target_chars(102, 7.5, 10), ls.target_chars(62, 7.5, 5))
        self.assertGreater(ls.target_chars(30, 7.5, 1), 60)

    def test_headline_count_words_up_to_ten(self):
        d = reply(names=NAMES10, per=10)
        d["hookCard"]["headline"], d["hookCard"]["highlight"] = "딱 열 가지만", ""
        texts = [ls.split_emphasis(x)[0] for x in ls._flat_lines(d)]
        problems = ls.check_script(d, n=10, given=[], max_sentence=30, target=sum(len("".join(t.split())) for t in texts),
                                   has_facts=False)
        self.assertFalse([p for p in problems if "개수" in p], problems)

    def test_two_line_items_for_ten(self):
        d = reply(names=NAMES10, per=10)
        for it in d["items"]:
            it["lines"] = it["lines"][:2]
        texts = [ls.split_emphasis(x)[0] for x in ls._flat_lines(d)]
        d["hookCard"]["headline"], d["hookCard"]["highlight"] = "꼭 쓸 10개", "10개"
        problems = ls.check_script(d, n=10, given=[], max_sentence=30, target=sum(len("".join(t.split())) for t in texts),
                                   has_facts=False)
        self.assertEqual(problems, [])

    def test_frame_props_allow_one_to_ten(self):
        self.assertEqual(check_props("LHookReveal", {"kicker": "k", "headline": "1개", "count": 1}), [])
        self.assertEqual(check_props("LHookReveal", {"kicker": "k", "headline": "10개", "count": 10}), [])
        self.assertTrue(check_props("LHookReveal", {"kicker": "k", "headline": "11개", "count": 11}))
        self.assertEqual(check_props("LRecap", {"title": "t", "items": [{"name": n} for n in NAMES10]}), [])

    def test_top_count_range(self):
        for text, n in (("주제, 1", 1), ("주제, 10", 10), ("주제", 5)):
            self.assertEqual(parse_request(text, default=5, lo=1, hi=10, unit="항목").count, n)
        for text in ("주제, 11", "주제, 0"):
            with self.assertRaises(ValueError):
                parse_request(text, default=5, lo=1, hi=10, unit="항목")


class CountFlowTest(ListicleCase):
    def test_target_duration_scales_with_count(self):
        for count, sec in ((1, 30), (5, 62), (10, 102)):
            res = self.post("/listicle", {"topic": f"깃 기본 명령어 {count}", "count": count})
            self.assertEqual(res.status_code, 201, res.text)
            job_id = res.json()["id"]
            self.run_step(job_id, "topic")
            self.assertEqual(self.read(job_id, "job.json")["targetDurationSec"], sec, count)
        self.assertEqual(self.post("/listicle", {"topic": "x", "count": 11}).status_code, 422)

    def test_top_accepts_ten(self):
        self.top("/top 깃 기본 명령어, 10")
        jobs = self.get("/jobs?status=PENDING").json()["items"]
        self.assertEqual(jobs[0]["topic"], "깃 기본 명령어")
        from app.db.models import Job
        with self.app.state.db() as s:
            self.assertEqual(s.get(Job, jobs[0]["id"]).input["listicle"]["count"], 10)


if __name__ == "__main__":
    unittest.main()
