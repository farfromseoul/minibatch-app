"""시범 운영 자동화 (아키텍처 D27, D24 변경, 2026-10-16).

다음 화 미리 만들기, 승인은 화 순서대로, 반려되면 뒤 화 정리, 미리 만든 화의 대본 입력, 시리즈 목록, 제목 없는 계획 생성.
"""
import json

from app.db.models import Job
from tests.fakes import FakeLlm, FakeRegistry
from tests.helpers import AppTestCase

SERIES = {
    "key": "ai-office", "category": "ai-it", "title": "민지의 AI 적응기",
    "bible": {"premise": "민지가 매화 개념 하나씩 배운다"},
    "episodes": [{"number": 1, "title": "배우기", "outline": "학습"},
                 {"number": 2, "title": "판단하기", "outline": "추론"},
                 {"number": 3, "title": "틀리기", "outline": "편향"}],
}


class ScriptWithStory:
    """대본 단계 대신: job.json 의 앞 화 이야기를 받은 그대로 script.json 에 남긴다 (요약·예고는 화 번호로)"""
    name, inputs, outputs = "script", ["job.json"], ["script.json"]

    def run(self, ctx):
        series = ctx.read_json("job.json")["series"] or {}
        n = series.get("episode")
        ctx.write_json("script.json", {"episodeSummary": f"{n}화 요약", "nextTeaser": f"{n}화 예고",
                                       "seenPrevious": series.get("previous", [])})


class AheadCase(AppTestCase):
    def make_steps(self):
        steps = super().make_steps()
        steps["script"] = ScriptWithStory()
        return steps

    def setUp(self):
        super().setUp()
        self.assertEqual(self.post("/series", SERIES).status_code, 201)

    def produce(self, until="review"):
        res = self.post("/jobs", {"seriesId": "ai-office"})
        self.assertEqual(res.status_code, 201, res.text)
        job_id = res.json()["id"]
        if until:
            self.run_until(job_id, until)
        return job_id

    def status(self, job_id):
        return self.get(f"/jobs/{job_id}").json()["status"]


class ProduceAheadTest(AheadCase):
    def test_episodes_are_made_ahead_and_story_uses_unapproved_script(self):
        ep1 = self.produce()
        ep2 = self.produce()  # 1화 승인 전
        ep3 = self.produce()

        self.assertEqual([self.status(j) for j in (ep1, ep2, ep3)], ["REVIEW"] * 3)
        seen = json.loads((self.job_dir(ep3) / "script.json").read_text())["seenPrevious"]
        # 승인 전이라 DB 에 요약이 없으면 앞 화 대본(script.json)의 요약을 쓴다
        self.assertEqual(seen, [{"episode": 1, "title": "배우기", "summary": "1화 요약"},
                                {"episode": 2, "title": "판단하기", "summary": "2화 요약"}])

    def test_failed_previous_episode_blocks_next(self):
        ep1 = self.produce(until="topic")
        with self.app.state.db() as s:
            s.get(Job, ep1).status = "FAILED"
            s.commit()

        res = self.post("/jobs", {"seriesId": "ai-office"})

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "previous_episode_not_ready")

    def test_auto_selection_makes_next_episode_ahead(self):
        ep1 = self.post("/jobs", {}).json()["id"]
        self.run_until(ep1, "review")

        nxt = self.post("/jobs", {}).json()

        self.assertEqual((nxt["seriesId"], nxt["episodeNumber"]), ("ai-office", 2))


class ApproveInOrderTest(AheadCase):
    def test_later_episode_cannot_be_approved_first(self):
        ep1 = self.produce()
        ep2 = self.produce()

        early = self.post(f"/jobs/{ep2}/approve", {"approvedBy": "운영자"})
        self.post(f"/jobs/{ep1}/approve", {"approvedBy": "운영자"})
        later = self.post(f"/jobs/{ep2}/approve", {"approvedBy": "운영자"})

        self.assertEqual(early.status_code, 409)
        self.assertEqual(early.json()["error"]["code"], "previous_episode_not_approved")
        self.assertEqual(self.status(ep2), "APPROVED")
        self.assertEqual(later.status_code, 200)


class RejectCascadeTest(AheadCase):
    def test_reject_discards_later_unpublished_episodes_and_resume_restarts_there(self):
        ep1 = self.produce()
        self.post(f"/jobs/{ep1}/approve", {"approvedBy": "운영자"})
        ep2 = self.produce()
        ep3 = self.produce(until="topic")  # 아직 만드는 중

        self.post(f"/jobs/{ep2}/reject", {"rejectedBy": "운영자", "reason": "설명이 틀림"})

        self.assertEqual((self.status(ep1), self.status(ep2), self.status(ep3)), ("APPROVED", "REJECTED", "REJECTED"))
        events = self.get(f"/jobs/{ep3}").json()["events"]
        self.assertIn("2화 반려", events[-1]["reason"])
        s = self.get("/series/ai-office").json()
        self.assertEqual(s["status"], "PAUSED")
        self.assertEqual([e["status"] for e in s["episodes"]], ["APPROVED", "REJECTED", "REJECTED"])
        self.assertEqual(self.run_step(ep3, "script").status_code, 409)  # 정리된 작업은 더 진행하지 않는다

        self.post("/series/ai-office/resume")
        again = self.post("/jobs", {"seriesId": "ai-office"})

        self.assertEqual(again.json()["episodeNumber"], 2)
        self.assertEqual([e["status"] for e in self.get("/series/ai-office").json()["episodes"]],
                         ["APPROVED", "IN_PRODUCTION", "PLANNED"])

    def test_job_rejected_while_last_step_runs_stays_rejected(self):
        ep1 = self.produce(until="script")

        class RejectDuring:
            name, inputs, outputs = "review", ["script.json"], ["review.json"]

            def run(self, ctx):  # 마지막 단계가 도는 사이 다른 요청이 반려한 것처럼
                with ctx.db() as s:
                    s.get(Job, ctx.job_id).status = "REJECTED"
                    s.commit()
                ctx.write_json("review.json", {})

        self.app.state.runner.steps["review"] = RejectDuring()
        self.run_step(ep1, "review")

        self.assertEqual(self.status(ep1), "REJECTED")  # REVIEW 로 덮지 않는다


class SeriesListTest(AheadCase):
    def test_lists_series_with_episode_counts(self):
        ep1 = self.produce()
        self.post(f"/jobs/{ep1}/approve", {"approvedBy": "운영자"})
        self.produce()

        res = self.get("/series")

        self.assertEqual(res.status_code, 200)
        (item,) = res.json()["items"]
        self.assertEqual(item["id"], "ai-office")
        self.assertEqual(item["status"], "ACTIVE")
        self.assertEqual(item["counts"], {"total": 3, "planned": 1, "inProduction": 1, "approved": 1, "rejected": 0})

    def test_filter_by_status(self):
        self.assertEqual(self.get("/series?status=PROPOSED").json()["items"], [])
        self.assertEqual(len(self.get("/series?status=APPROVED").json()["items"]), 1)


PLAN = {"title": "민준의 데이터 탐험", "bible": {"premise": "p", "tone": "t", "characters": [{"name": "민준", "role": "신입"}]},
        "episodes": [{"title": "데이터란", "outline": "a"}, {"title": "표와 열", "outline": "b"}]}


class PlanWithoutTitleTest(AppTestCase):
    def make_providers(self):
        self.llm = FakeLlm(PLAN)
        return FakeRegistry(self.llm)

    def test_llm_makes_title_and_key_is_generated(self):
        res = self.post("/series", {"category": "ai-it", "episodeCount": 2})

        self.assertEqual(res.status_code, 201, res.text)
        body = res.json()
        self.assertEqual(body["title"], "민준의 데이터 탐험")
        self.assertEqual(body["id"], "s20261016-1")  # 시계 2026-10-16 (한국 날짜), 그날 첫 시리즈
        self.assertEqual(body["status"], "PROPOSED")
        self.assertEqual(self.llm.requests[0]["schema"]["required"], ["title", "bible", "episodes"])

    def test_recent_series_titles_are_given_to_avoid_repeats(self):
        self.post("/series", {"key": "old", "category": "ai-it", "title": "예전 시리즈",
                              "episodes": [{"number": 1, "title": "x", "outline": "y"}]})

        self.post("/series", {"category": "ai-it", "episodeCount": 2})

        self.assertIn("예전 시리즈", self.llm.last_user_text())
