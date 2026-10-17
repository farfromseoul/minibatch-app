"""취소 정책 (아키텍처 D29, 2026-10-17 사용자 요청).

작업 취소: 공개 전 작업을 CANCELLED 로. 다시 실행하지 않는다. 시리즈 화면 그 화도 CANCELLED, 시리즈는 PAUSED.
시리즈 취소: 시리즈를 CANCELLED 로. 안 만든 화·공개 전 작업도 CANCELLED. 공개된 화는 그대로.
"""
from app.db.models import Job
from tests.helpers import AppTestCase

SERIES = {"key": "s1", "category": "ai-it", "title": "시리즈",
          "episodes": [{"number": 1, "title": "1화", "outline": "a"}, {"number": 2, "title": "2화", "outline": "b"},
                       {"number": 3, "title": "3화", "outline": "c"}]}


class CancelCase(AppTestCase):
    def status(self, job_id):
        return self.get(f"/jobs/{job_id}").json()["status"]

    def episodes(self, sid="s1"):
        return [e["status"] for e in self.get(f"/series/{sid}").json()["episodes"]]

    def set_status(self, job_id, status):
        with self.app.state.db() as s:
            s.get(Job, job_id).status = status
            s.commit()


class JobCancelTest(CancelCase):
    def test_waiting_job_is_cancelled_and_never_runs_again(self):
        job_id = self.new_job()
        self.run_until(job_id, "script")
        self.set_status(job_id, "WAITING")

        res = self.post(f"/jobs/{job_id}/cancel", {"cancelledBy": "운영자", "reason": "시리즈 정리"})

        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(self.status(job_id), "CANCELLED")
        ev = self.get(f"/jobs/{job_id}").json()["events"][-1]
        self.assertEqual((ev["to"], ev["actor"], ev["reason"]), ("CANCELLED", "운영자", "시리즈 정리"))
        self.assertEqual(self.run_step(job_id, "review").json()["error"]["code"], "job_not_runnable")
        self.assertEqual(self.post(f"/jobs/{job_id}/reset?from=script").status_code, 409)

    def test_published_job_cannot_be_cancelled(self):
        job_id = self.new_job()
        self.set_status(job_id, "PUBLISHED")

        res = self.post(f"/jobs/{job_id}/cancel", {"cancelledBy": "운영자", "reason": "x"})

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "not_cancellable")

    def test_cancelled_topic_can_be_made_again(self):
        job_id = self.new_job("같은 주제")
        self.post(f"/jobs/{job_id}/cancel", {"cancelledBy": "운영자", "reason": "x"})

        self.assertEqual(self.post("/jobs", {"topic": "같은 주제"}).status_code, 201)  # 중복 검사에서 빠진다

    def test_cancel_while_step_runs_stays_cancelled(self):
        job_id = self.new_job()
        self.run_until(job_id, "script")

        class CancelDuring:
            name, inputs, outputs = "review", ["script.json"], ["review.json"]

            def run(self, ctx):
                with ctx.db() as s:
                    s.get(Job, ctx.job_id).status = "CANCELLED"
                    s.commit()
                raise RuntimeError("도는 사이 취소")

        self.app.state.runner.steps["review"] = CancelDuring()
        self.run_step(job_id, "review")

        self.assertEqual(self.status(job_id), "CANCELLED")  # 실패 기록이 FAILED 로 덮지 않는다

    def test_episode_cancel_pauses_series(self):
        self.post("/series", SERIES)
        ep1 = self.post("/jobs", {"seriesId": "s1"}).json()["id"]

        self.post(f"/jobs/{ep1}/cancel", {"cancelledBy": "운영자", "reason": "x"})

        self.assertEqual(self.get("/series/s1").json()["status"], "PAUSED")
        self.assertEqual(self.episodes(), ["CANCELLED", "PLANNED", "PLANNED"])
        self.post("/series/s1/resume")  # 다시 진행하면 취소한 화부터 다시 만든다
        self.assertEqual(self.post("/jobs", {"seriesId": "s1"}).json()["episodeNumber"], 1)


class SeriesCancelTest(CancelCase):
    def test_series_cancel_cancels_unpublished_and_keeps_published(self):
        self.post("/series", SERIES)
        ep1 = self.post("/jobs", {"seriesId": "s1"}).json()["id"]
        self.run_until(ep1, "review")
        self.post(f"/jobs/{ep1}/approve", {"approvedBy": "운영자"})
        self.set_status(ep1, "PUBLISHED")
        ep2 = self.post("/jobs", {"seriesId": "s1"}).json()["id"]
        self.set_status(ep2, "WAITING")

        res = self.post("/series/s1/cancel", {"cancelledBy": "운영자", "reason": "시리즈 정리"})

        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["status"], "CANCELLED")
        self.assertEqual((self.status(ep1), self.status(ep2)), ("PUBLISHED", "CANCELLED"))
        self.assertEqual(self.episodes(), ["APPROVED", "CANCELLED", "CANCELLED"])
        nxt = self.post("/jobs", {"seriesId": "s1"})
        self.assertEqual((nxt.status_code, nxt.json()["error"]["code"]), (409, "series_cancelled"))

    def test_approved_series_without_jobs_is_cancelled_and_skipped_by_auto_selection(self):
        self.post("/series", SERIES)

        self.post("/series/s1/cancel", {"cancelledBy": "운영자", "reason": "새 형식으로 다시"})

        self.assertEqual(self.episodes(), ["CANCELLED"] * 3)
        auto = self.post("/jobs", {})
        self.assertEqual((auto.status_code, auto.json()["error"]["code"]), (409, "no_candidates"))
        self.assertEqual(self.get("/series?status=CANCELLED").json()["items"][0]["id"], "s1")

    def test_done_series_cannot_be_cancelled(self):
        self.post("/series", dict(SERIES, key="s2", episodes=SERIES["episodes"][:1]))
        ep = self.post("/jobs", {"seriesId": "s2"}).json()["id"]
        self.run_until(ep, "review")
        self.post(f"/jobs/{ep}/approve", {"approvedBy": "운영자"})

        res = self.post("/series/s2/cancel", {"cancelledBy": "운영자", "reason": "x"})

        self.assertEqual((res.status_code, res.json()["error"]["code"]), (409, "not_cancellable"))
