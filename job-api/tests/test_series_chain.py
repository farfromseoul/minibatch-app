"""시리즈를 차례대로 (아키텍처 D33, 2026-10-18).

2026-10-17~18 실제: 1번째 시리즈 10화가 검토에 떨어진 채 남았는데 다음 시리즈 1화가 만들어져 공개됐고,
다음 시리즈 계획이 이미 공개한 주제('토큰이란 무엇일까?')를 다시 넣어 중복 검사에 걸려 생산이 멈췄다.
앞 시리즈의 모든 화가 만들어져야 다음 시리즈를 만들고, 승인·업로드도 시리즈 순서대로 한다.
"""
from app.db.models import Job
from tests.fakes import FakeLlm, FakeRegistry
from tests.helpers import AppTestCase
from tests.test_series_ahead import ScriptWithStory
from tests.test_upload_order import QUOTA, OrderCase


def series(key, title, *titles):
    return {"key": key, "category": "ai-it", "title": title, "bible": {"premise": "매화 개념 하나"},
            "episodes": [{"number": i, "title": t, "outline": t} for i, t in enumerate(titles, start=1)]}


class ChainCase(AppTestCase):
    def make_steps(self):
        steps = super().make_steps()
        steps["script"] = ScriptWithStory()
        return steps

    def setUp(self):
        super().setUp()
        self.assertEqual(self.post("/series", series("first", "AI 원리", "학습", "추론")).status_code, 201)
        self.clock.advance(minutes=1)
        self.assertEqual(self.post("/series", series("second", "AI 서비스", "검색", "추천")).status_code, 201)

    def produce(self, key, until="review"):
        res = self.post("/jobs", {"seriesId": key})
        self.assertEqual(res.status_code, 201, res.text)
        job_id = res.json()["id"]
        if until:
            self.run_until(job_id, until)
        return job_id

    def approve(self, job_id):
        return self.post(f"/jobs/{job_id}/approve", {"approvedBy": "운영자"})


class SequenceTest(ChainCase):
    def test_series_are_numbered_in_approval_order_without_cancelled(self):
        self.clock.advance(minutes=1)
        self.post("/series", series("dropped", "버린 시리즈", "x"))
        self.post("/series/dropped/cancel", {"cancelledBy": "운영자", "reason": "주제 겹침"})
        self.clock.advance(minutes=1)
        self.post("/series", series("third", "AI 보안", "공격"))

        seq = {k: self.get(f"/series/{k}").json()["sequence"] for k in ("first", "second", "dropped", "third")}

        self.assertEqual(seq, {"first": 1, "second": 2, "dropped": None, "third": 3})
        listed = {i["id"]: i["sequence"] for i in self.get("/series").json()["items"]}
        self.assertEqual(listed["third"], 3)


class ProductionOrderTest(ChainCase):
    def test_next_series_waits_until_every_episode_of_previous_is_made(self):
        self.produce("first")

        blocked = self.post("/jobs", {"seriesId": "second"})
        self.produce("first")
        allowed = self.post("/jobs", {"seriesId": "second"})

        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["error"]["code"], "previous_series_not_finished")
        self.assertIn("1번째 시리즈 'AI 원리' 2화", blocked.json()["error"]["message"])
        self.assertEqual(allowed.status_code, 201, allowed.text)

    def test_failed_last_episode_of_previous_series_blocks_and_is_reported(self):
        self.produce("first")
        last = self.produce("first", until=None)
        with self.app.state.db() as s:
            s.get(Job, last).status = "FAILED"
            s.commit()

        res = self.post("/jobs", {})

        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "no_candidates")
        self.assertIn("2화", res.json()["error"]["message"])  # 왜 못 만드는지 알린다 (텔레그램 알림 문구)
        self.assertIn("FAILED", res.json()["error"]["message"])

    def test_skipped_reasons_are_reported_when_nothing_can_be_made(self):
        self.produce("first")
        self.produce("first", until="script")  # 2화 제작 중

        res = self.post("/jobs", {})

        self.assertEqual(res.json()["error"]["code"], "no_candidates")
        self.assertIn("AI 서비스", res.json()["error"]["message"])


class ApprovalOrderTest(ChainCase):
    def test_first_episode_of_next_series_is_approved_only_after_previous_series_is_done(self):
        a1, a2 = self.produce("first"), self.produce("first")
        b1 = self.produce("second")

        early = self.approve(b1)
        self.approve(a1)
        self.approve(a2)
        later = self.approve(b1)

        self.assertEqual(early.status_code, 409)
        self.assertEqual(early.json()["error"]["code"], "previous_series_not_done")
        self.assertEqual(later.status_code, 200, later.text)
        self.assertEqual(self.get("/series/first").json()["status"], "DONE")


class CrossSeriesUploadTest(OrderCase):
    def setUp(self):
        super().setUp()  # s1: 1~3화
        self.clock.advance(minutes=1)
        self.assertEqual(self.post("/series", series("s2", "다음 시리즈", "검색")).status_code, 201)

    def test_next_series_first_episode_uploads_after_previous_series_last_episode(self):
        self.yt.fail["upload_video"] = QUOTA
        for _ in range(3):
            self.episode()
        b1 = self.post("/jobs", {"seriesId": "s2"}).json()["id"]

        self.run_until(b1, "upload")

        st = self.status(b1, "upload")
        self.assertEqual((st["status"], st["kind"]), ("failed", "blocked"))
        self.assertIn("1번째 시리즈", st["error"])
        self.assertIn("3화", st["error"])


PLAN = {"title": "AI 서비스의 뒷면", "bible": {"premise": "p", "tone": "t"},
        "episodes": [{"title": "검색은 어떻게 고를까", "outline": "a"}, {"title": "추천은 어떻게 고를까", "outline": "b"}]}


class PlanContinuityTest(AppTestCase):
    def make_providers(self):
        self.llm = FakeLlm()
        return FakeRegistry(self.llm)

    def setUp(self):
        super().setUp()
        self.post("/series", series("first", "AI 원리", "토큰이란 무엇일까?", "임베딩이란?"))
        self.post("/series", series("dropped", "버린 시리즈", "버린 화"))
        self.post("/series/dropped/cancel", {"cancelledBy": "운영자", "reason": "x"})

    def test_plan_gets_previous_series_and_used_topics_and_continues_from_it(self):
        self.llm.responses = [PLAN]

        res = self.post("/series", {"category": "ai-it", "episodeCount": 2})

        self.assertEqual(res.status_code, 201, res.text)
        prompt = self.llm.last_user_text()
        self.assertIn("2번째 시리즈", prompt)
        self.assertIn("1번째 시리즈 'AI 원리'", prompt)  # 이어받을 앞 시리즈
        self.assertIn("토큰이란 무엇일까?", prompt)  # 다시 다루면 안 되는 주제
        self.assertNotIn("버린 화", prompt)  # 취소한 시리즈는 앞 시리즈가 아니다

    def test_plan_repeating_a_used_topic_is_asked_again(self):
        repeat = dict(PLAN, episodes=[{"title": "토큰이란 무엇일까?", "outline": "a"}, PLAN["episodes"][1]])
        self.llm.responses = [repeat, PLAN]

        res = self.post("/series", {"category": "ai-it", "episodeCount": 2})

        self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(len(self.llm.requests), 2)
        self.assertIn("토큰이란 무엇일까?", self.llm.last_user_text())
        self.assertEqual(res.json()["episodes"][0]["title"], "검색은 어떻게 고를까")

    def test_episode_number_prefix_in_titles_is_removed(self):
        numbered = dict(PLAN, episodes=[{"title": "1화 검색은 어떻게 고를까", "outline": "a"},
                                        {"title": "2화. 추천은 어떻게 고를까", "outline": "b"}])
        self.llm.responses = [numbered]

        res = self.post("/series", {"category": "ai-it", "episodeCount": 2})

        # 2026-10-18 실제: 'N화 ' 가 붙어 검토 알림이 '1화 1화 …' 로 나왔다. 화 번호는 코드가 매긴다
        self.assertEqual([e["title"] for e in res.json()["episodes"]], ["검색은 어떻게 고를까", "추천은 어떻게 고를까"])
