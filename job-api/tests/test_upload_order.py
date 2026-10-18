"""업로드 대기 중에도 다음 화를 미리 만들고, 업로드는 화 순서대로 (아키텍처 D31, 2026-10-17).

2026-10-17 실제: 1화가 채널 업로드 한도(uploadLimitExceeded)로 WAITING 이 되자 2~10화 제작도 멈췄다.
제작은 앞서가고, 업로드만 앞 화가 올라간 뒤에 한다. 무엇을 이어 할지는 GET /jobs/next 가 정한다.
"""
from datetime import datetime, timedelta

from app.db.models import Job
from app.youtube.client import YouTubeError
from tests.test_qc_upload import PublishCase

SERIES = {"key": "s1", "title": "AI 원리 10화", "bible": {"premise": "매화 개념 하나"},
          "episodes": [{"number": 1, "title": "학습", "outline": "a"}, {"number": 2, "title": "추론", "outline": "b"},
                       {"number": 3, "title": "편향", "outline": "c"}]}
QUOTA = YouTubeError("quota", "업로드 한도", 400, "uploadLimitExceeded")


class OrderCase(PublishCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.post("/series", SERIES).status_code, 201)

    def episode(self, until="upload"):
        res = self.post("/jobs", {"seriesId": "s1"})
        self.assertEqual(res.status_code, 201, res.text)
        job_id = res.json()["id"]
        if until:
            self.run_until(job_id, until)
        return job_id

    def job(self, job_id):
        return self.get(f"/jobs/{job_id}").json()

    def next_job(self):
        res = self.get("/jobs/next")
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["jobId"]

    def after_quota_reset(self):
        retry_at = self.status_of_upload_retry()
        self.clock.now = datetime.strptime(retry_at, "%Y-%m-%dT%H:%M:%SZ") + timedelta(minutes=1)

    def status_of_upload_retry(self):
        with self.app.state.db() as s:
            ids = [j.id for j in s.query(Job).filter(Job.status == "WAITING")]
        for job_id in ids:
            st = self.status(job_id, "upload")
            if st["kind"] == "quota":
                return st["retryAt"]
        raise AssertionError("한도 대기 작업이 없다")


class MakeAheadTest(OrderCase):
    def test_next_episode_is_made_while_previous_waits_for_upload_quota(self):
        self.yt.fail["upload_video"] = QUOTA
        ep1 = self.episode()
        self.assertEqual(self.job(ep1)["status"], "WAITING")

        res = self.post("/jobs", {"seriesId": "s1"})

        self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(res.json()["episodeNumber"], 2)

    def test_previous_episode_still_in_production_blocks_next(self):
        self.episode(until="render")  # qc·upload 전

        res = self.post("/jobs", {"seriesId": "s1"})

        self.assertEqual((res.status_code, res.json()["error"]["code"]), (409, "previous_episode_not_ready"))


class UploadOrderTest(OrderCase):
    def test_episode_upload_waits_until_previous_is_uploaded(self):
        self.yt.fail["upload_video"] = QUOTA
        self.episode()
        ep2 = self.episode()

        st = self.status(ep2, "upload")
        self.assertEqual((st["status"], st["kind"]), ("failed", "blocked"))
        self.assertIn("1화", st["error"])
        self.assertEqual(self.job(ep2)["status"], "WAITING")
        self.assertEqual(self.yt.uploaded, 0)  # 1화보다 먼저 올리지 않는다
        self.assertIn("1화", self.job(ep2)["blockedBy"])

    def test_blocked_episode_uploads_after_previous_in_order(self):
        self.yt.fail["upload_video"] = QUOTA
        ep1 = self.episode()
        ep2 = self.episode()
        self.after_quota_reset()

        self.run_step(ep1, "upload")
        self.assertIsNone(self.job(ep2)["blockedBy"])
        self.run_step(ep2, "upload")

        self.assertEqual([self.job(j)["status"] for j in (ep1, ep2)], ["REVIEW", "REVIEW"])
        self.assertEqual(self.yt.playlist["PL1"], ["VID1", "VID2"])

    def test_standalone_job_is_not_blocked(self):
        self.yt.fail["upload_video"] = QUOTA
        self.episode()
        solo = self.new_job("단독 주제")

        self.run_until(solo, "upload")

        self.assertEqual(self.job(solo)["status"], "REVIEW")


class NextJobTest(OrderCase):
    def test_unfinished_job_comes_first(self):
        ep1 = self.episode(until="render")

        self.assertEqual(self.next_job(), ep1)

    def test_nothing_to_continue(self):
        self.assertIsNone(self.next_job())

    def test_waiting_jobs_are_skipped_until_they_can_go_on(self):
        self.yt.fail["upload_video"] = QUOTA
        ep1 = self.episode()
        ep2 = self.episode()

        self.assertIsNone(self.next_job())  # 1화는 한도 대기, 2화는 1화 대기 → 새 화를 만들러 간다
        self.after_quota_reset()
        self.assertEqual(self.next_job(), ep1)
        self.run_step(ep1, "upload")
        self.assertEqual(self.next_job(), ep2)

    def test_skipped_jobs_are_listed_with_reason(self):
        self.yt.fail["upload_video"] = QUOTA
        ep1 = self.episode()

        body = self.get("/jobs/next").json()

        self.assertEqual([s["id"] for s in body["skipped"]], [ep1])
        self.assertIn("한도", body["skipped"][0]["reason"])


class BacklogTest(OrderCase):
    def test_jobs_waiting_for_upload_count_toward_backlog(self):
        self.yt.fail["upload_video"] = QUOTA
        self.episode()
        with self.app.state.db() as s:  # 어제 만든 작업 5개가 업로드 대기 (하루 한도와 섞이지 않게 어제로)
            for i in range(5):
                job = Job(id=f"short-20261015-{i:03d}", topic=f"주제{i}", topic_key=f"k{i}", category="ai-it",
                          status="WAITING", current_step="upload", video_engine="remotion", input={},
                          created_at=self.clock.now - timedelta(days=1), updated_at=self.clock.now)
                s.add(job)
            s.commit()

        res = self.post("/jobs", {})

        self.assertEqual((res.status_code, res.json()["error"]["code"]), (409, "review_backlog_full"))
