"""작업 만들기: 직접 주제, 중복 검사, 자동 선정, 하루 한도, 조회."""
from tests.helpers import AppTestCase


class CreateJobTest(AppTestCase):
    def test_creates_job_with_dated_id_and_pending_status(self):
        res = self.post("/jobs", {"topic": "RAG란?"})

        self.assertEqual(res.status_code, 201, res.text)
        job = res.json()
        self.assertEqual(job["id"], "short-20261016-001")  # 한국 날짜 기준
        self.assertEqual(job["status"], "PENDING")
        self.assertEqual(job["category"], "ai-it")
        self.assertEqual(job["topic"], "RAG란?")

    def test_ids_count_up_within_a_day(self):
        self.new_job("RAG란?")

        second = self.new_job("임베딩이란?")

        self.assertEqual(second, "short-20261016-002")

    def test_rejects_duplicate_topic_in_progress(self):
        self.new_job("RAG란?")

        res = self.post("/jobs", {"topic": "rag 란"})  # 공백·대소문자·조사가 달라도 같은 주제

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "duplicate_topic")

    def test_allows_same_topic_after_30_days(self):
        self.new_job("RAG란?")
        self.clock.advance(days=31)

        res = self.post("/jobs", {"topic": "RAG란?"})

        self.assertEqual(res.status_code, 201)

    def test_unknown_category_is_rejected(self):
        res = self.post("/jobs", {"topic": "여행지", "category": "travel"})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "unknown_category")


class AutoSelectTest(AppTestCase):
    def test_no_candidates_returns_409(self):
        res = self.post("/jobs", {})

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "no_candidates")

    def test_picks_oldest_ready_topic_and_marks_it_used(self):
        self.post("/topics", {"category": "ai-it", "titles": ["임베딩이란?", "토큰이란?"]})

        res = self.post("/jobs", {})

        self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(res.json()["topic"], "임베딩이란?")
        topics = self.get("/topics?status=USED").json()["items"]
        self.assertEqual([t["title"] for t in topics], ["임베딩이란?"])

    def test_daily_limit_applies_to_auto_selection(self):
        self.post("/topics", {"category": "ai-it", "titles": ["가", "나", "다", "라"]})
        for _ in range(3):
            self.assertEqual(self.post("/jobs", {}).status_code, 201)

        res = self.post("/jobs", {})

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "daily_limit_reached")


class ReadJobTest(AppTestCase):
    def test_get_job_and_list_by_status(self):
        job_id = self.new_job()

        one = self.get(f"/jobs/{job_id}").json()
        listed = self.get("/jobs?status=PENDING").json()["items"]

        self.assertEqual(one["id"], job_id)
        self.assertEqual(one["steps"], [])
        self.assertEqual([j["id"] for j in listed], [job_id])
        self.assertEqual(self.get("/jobs?status=REVIEW").json()["items"], [])
