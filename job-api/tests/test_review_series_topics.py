"""승인·반려, 시리즈 연속 규칙(D24), 주제 출처(D25)."""
import json

from tests.helpers import AppTestCase

SERIES = {
    "key": "ai-office",
    "category": "ai-it",
    "title": "신입 개발자 민지의 AI 적응기",
    "bible": {"premise": "민지가 매화 개념 하나씩 배운다", "characters": [{"name": "민지", "role": "신입"}]},
    "episodes": [
        {"number": 1, "title": "AI가 뭐길래", "outline": "AI의 뜻"},
        {"number": 2, "title": "머신러닝은 뭐가 달라", "outline": "규칙 대신 데이터"},
        {"number": 3, "title": "딥러닝 한 걸음", "outline": "층을 쌓는다"},
    ],
}


class ApprovalTest(AppTestCase):
    def test_approve_only_in_review(self):
        job_id = self.new_job()

        res = self.post(f"/jobs/{job_id}/approve", {"approvedBy": "운영자"})

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "not_in_review")

    def test_approve_records_who_and_when(self):
        job_id = self.new_job()
        self.run_until(job_id, "review")

        res = self.post(f"/jobs/{job_id}/approve",
                        {"approvedBy": "운영자", "publishAt": "2026-10-17T09:00:00+09:00"})

        self.assertEqual(res.status_code, 200, res.text)
        job = self.get(f"/jobs/{job_id}").json()
        self.assertEqual(job["status"], "APPROVED")
        self.assertEqual(job["publication"]["approvedBy"], "운영자")
        self.assertIsNotNone(job["publication"]["approvedAt"])
        self.assertEqual(job["publication"]["publishAt"], "2026-10-17T00:00:00")  # UTC 로 저장
        self.assertEqual([e["to"] for e in job["events"]][-1], "APPROVED")

    def test_reject_records_reason(self):
        job_id = self.new_job()
        self.run_until(job_id, "review")

        self.post(f"/jobs/{job_id}/reject", {"rejectedBy": "운영자", "reason": "비유가 틀렸다"})

        job = self.get(f"/jobs/{job_id}").json()
        self.assertEqual(job["status"], "REJECTED")
        self.assertEqual(job["events"][-1]["reason"], "비유가 틀렸다")


class SeriesTest(AppTestCase):
    def create_series(self, body=SERIES):
        res = self.post("/series", body)
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()["id"]

    def produce_and_review(self, series_id):
        res = self.post("/jobs", {"seriesId": series_id})
        self.assertEqual(res.status_code, 201, res.text)
        job_id = res.json()["id"]
        self.run_until(job_id, "review")
        return job_id

    def test_user_written_plan_is_approved_at_once(self):
        series_id = self.create_series()

        s = self.get(f"/series/{series_id}").json()

        self.assertEqual(s["status"], "APPROVED")
        self.assertEqual(s["planSource"], "user")
        self.assertEqual([e["status"] for e in s["episodes"]], ["PLANNED"] * 3)

    def test_plan_generation_without_llm_settings_is_503(self):
        res = self.post("/series", {"key": "x", "category": "ai-it", "title": "제목만", "episodeCount": 5})

        self.assertEqual(res.status_code, 503)  # 이 테스트는 providers.yaml 없이 돈다 (생성은 tests/test_generation.py)

    def test_next_episode_waits_for_previous_approval(self):
        series_id = self.create_series()
        job1 = self.produce_and_review(series_id)

        blocked = self.post("/jobs", {"seriesId": series_id})
        self.post(f"/jobs/{job1}/approve", {"approvedBy": "운영자"})
        allowed = self.post("/jobs", {"seriesId": series_id})

        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["error"]["code"], "previous_episode_not_approved")
        self.assertEqual(allowed.status_code, 201)
        self.assertEqual(allowed.json()["episodeNumber"], 2)
        self.assertEqual(allowed.json()["topic"], "머신러닝은 뭐가 달라")

    def test_episode_job_json_carries_story_so_far(self):
        series_id = self.create_series()
        job1 = self.produce_and_review(series_id)
        (self.job_dir(job1) / "script.json").write_text(json.dumps(
            {"episodeSummary": "민지가 AI의 뜻을 배웠다", "nextTeaser": "다음엔 머신러닝"}, ensure_ascii=False))
        self.post(f"/jobs/{job1}/approve", {"approvedBy": "운영자"})
        job2 = self.post("/jobs", {"seriesId": series_id}).json()["id"]

        self.run_step(job2, "topic")

        series = json.loads((self.job_dir(job2) / "job.json").read_text())["series"]
        self.assertEqual(series["episode"], 2)
        self.assertEqual(series["totalEpisodes"], 3)
        self.assertEqual(series["previous"], [{"episode": 1, "title": "AI가 뭐길래",
                                               "summary": "민지가 AI의 뜻을 배웠다"}])
        self.assertEqual(series["outline"], "규칙 대신 데이터")
        self.assertEqual(series["nextOutline"], "층을 쌓는다")
        self.assertEqual(series["bible"]["premise"], "민지가 매화 개념 하나씩 배운다")

    def test_rejection_pauses_series_and_resume_replans_episode(self):
        series_id = self.create_series()
        job1 = self.produce_and_review(series_id)

        self.post(f"/jobs/{job1}/reject", {"rejectedBy": "운영자", "reason": "다시"})
        paused = self.post("/jobs", {"seriesId": series_id})
        self.post(f"/series/{series_id}/resume")
        again = self.post("/jobs", {"seriesId": series_id})

        self.assertEqual(paused.status_code, 409)
        self.assertEqual(paused.json()["error"]["code"], "series_paused")
        self.assertEqual(again.status_code, 201)
        self.assertEqual(again.json()["episodeNumber"], 1)

    def test_last_episode_approval_finishes_series(self):
        body = dict(SERIES, episodes=SERIES["episodes"][:1])
        series_id = self.create_series(body)
        job1 = self.produce_and_review(series_id)

        self.post(f"/jobs/{job1}/approve", {"approvedBy": "운영자"})

        self.assertEqual(self.get(f"/series/{series_id}").json()["status"], "DONE")

    def test_auto_selection_prefers_series_then_topics(self):
        self.post("/topics", {"category": "ai-it", "titles": ["단독 주제"]})
        series_id = self.create_series()

        first = self.post("/jobs", {}).json()
        second = self.post("/jobs", {}).json()

        self.assertEqual(first["seriesId"], series_id)
        self.assertEqual(second["topic"], "단독 주제")  # 1화가 아직 승인 전이라 시리즈는 건너뛴다

    def test_episode_numbers_must_be_1_to_n(self):
        body = dict(SERIES, key="bad", episodes=[{"number": 2, "title": "x", "outline": "y"}])

        self.assertEqual(self.post("/series", body).status_code, 422)


class TopicsTest(AppTestCase):
    def test_user_topics_are_ready(self):
        res = self.post("/topics", {"category": "ai-it", "titles": ["토큰이란?", "토큰이란?"]})

        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["created"], 1)  # 같은 주제는 한 번만
        self.assertEqual([t["status"] for t in self.get("/topics?status=READY").json()["items"]], ["READY"])

    def test_proposed_topic_needs_approval(self):
        from app.db.models import Topic

        with self.app.state.db() as s:
            s.add(Topic(title="LLM이 제안한 주제", normalized_key="llm이제안한주제", category="ai-it",
                        source="llm", status="PROPOSED", created_at=self.clock()))
            s.commit()
        self.assertEqual(self.post("/jobs", {}).status_code, 409)  # 승인 전에는 고르지 않는다
        topic_id = self.get("/topics?status=PROPOSED").json()["items"][0]["id"]

        self.post(f"/topics/{topic_id}/approve")

        self.assertEqual(self.post("/jobs", {}).json()["topic"], "LLM이 제안한 주제")
