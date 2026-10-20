"""현황 한눈에 보기 (2026-10-20 사용자: n8n 만 봐서는 몇 화까지 만들었는지, 업로드에서 막혔는지, 계획이 보내졌는지 알 수 없다).

GET /overview 와 텔레그램 /status 가 같은 내용을 보여 준다.
"""
from tests.fakes import FakeLlm, FakeRegistry
from tests.helpers import FakeStep, StepFailure
from tests.test_telegram import PLAN, SERIES, TelegramCase


class OverviewCase(TelegramCase):
    def overview(self):
        res = self.get("/overview")
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    def episodes(self, ov):
        (series,) = [x for x in ov["series"] if x["status"] in ("ACTIVE", "APPROVED")]
        return {e["number"]: e for e in series["episodes"]}


class EpisodeStateTest(OverviewCase):
    def test_each_episode_says_where_it_is(self):
        self.post("/series", SERIES)
        ep1 = self.post("/jobs", {"seriesId": "ai-office"}).json()["id"]
        self.run_until(ep1, "review")

        eps = self.episodes(self.overview())

        self.assertEqual(eps[1]["state"], "REVIEW")
        self.assertIn("검토 대기", eps[1]["label"])
        self.assertEqual(eps[2]["state"], "PLANNED")
        self.assertIn("아직 안 만듦", eps[2]["label"])

    def test_text_lists_series_and_episodes(self):
        self.post("/series", SERIES)

        text = self.overview()["text"]

        self.assertIn("민지의 AI 적응기", text)
        self.assertIn("1화 배우기", text)
        self.assertIn("2화 판단하기", text)


class QuotaWaitTest(OverviewCase):
    def make_steps(self):
        steps = super().make_steps()
        steps["review"] = FakeStep("review", ["script.json"], ["review.json"],
                                   fail=StepFailure("quota", "업로드 세션 400 uploadLimitExceeded", retry_at="2026-10-17T07:05:00Z"))
        return steps

    def test_waiting_on_quota_shows_next_try_in_korean_time(self):
        self.post("/series", SERIES)
        ep1 = self.post("/jobs", {"seriesId": "ai-office"}).json()["id"]
        self.run_until(ep1, "review")

        e = self.episodes(self.overview())[1]

        self.assertEqual(e["state"], "WAITING")
        self.assertIn("한도", e["label"])
        self.assertIn("10-17 16:05", e["label"])  # 07:05Z = 한국 16:05


class PlanStateTest(OverviewCase):
    def make_providers(self):
        return FakeRegistry(FakeLlm(PLAN))

    def test_proposed_plan_shows_telegram_sent_time(self):
        sid = self.post("/series", {"category": "ai-it", "episodeCount": 2}).json()["id"]

        ov = self.overview()

        (plan,) = [x for x in ov["series"] if x["status"] == "PROPOSED"]
        self.assertEqual(plan["id"], sid)
        self.assertIsNotNone(plan["telegramSentAt"])
        self.assertIn("승인 대기", ov["text"])
        self.assertIn("텔레그램 보냄", ov["text"])
        self.assertIn("묻지 않음", ov["question"]["label"])  # 승인 대기 계획이 있어 주제를 묻지 않는다 (D37)


class StatusCommandTest(OverviewCase):
    def test_status_command_replies_with_overview(self):
        self.post("/series", SERIES)
        self.tg.say("/status")

        self.poll()

        self.assertIn("민지의 AI 적응기", self.tg.sent("sendMessage")[-1]["text"])

    def test_other_chat_status_is_ignored(self):
        self.tg.say("/status", chat="999")

        self.poll()

        self.assertEqual(self.tg.sent("sendMessage"), [])
