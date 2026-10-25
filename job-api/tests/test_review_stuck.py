"""대본 검토가 3번 연속 점수 미달이면 텔레그램으로 [개요 고쳐 다시][건너뛰기] 를 묻는다 (2026-10-21 사용자).

2026-10-21 실제: 4번째 시리즈 4화(키 합의)가 '구체성 2점'으로 세 번 떨어져 FAILED 로 멈췄고, 시리즈 전체가 멈췄다.
[개요 고쳐 다시]: LLM 이 검토 의견으로 개요를 고치고 주제 단계부터 되돌린다 → 생산 워크플로가 다시 만들고 승인 요청까지.
[건너뛰기]: 그 화를 건너뛴 화(SKIPPED)로 두고 다음 화로 넘어간다.
"""
from tests.fakes import FakeLlm, FakeRegistry
from tests.helpers import FakeStep, StepFailure
from tests.test_telegram import SERIES, TelegramCase

LOW = "검토 점수 미달: 구체성 2점 (3번: '공개 정보로 같은 비밀을 만드는 절차'라는 표현은 추상적입니다.)"


class StuckCase(TelegramCase):
    review_fails = True

    def setUp(self):
        self.llm = FakeLlm({"outline": "물감 섞기 비유: 공개된 노란색에 각자 비밀 색을 섞어 교환하면 둘만 같은 색이 된다"})
        super().setUp()

    def make_providers(self):
        return FakeRegistry(self.llm)

    def make_steps(self):
        steps = super().make_steps()
        if self.review_fails:
            steps["review"] = FakeStep("review", ["script.json"], ["review.json"],
                                       fail=StepFailure("deterministic", LOW, retry_from="script"))
        return steps

    def fail_review(self, job_id, times):
        """생산 워크플로처럼: 검토 실패 → script 부터 되돌려 다시 (times 번 실패)"""
        self.run_until(job_id, "review")
        for _ in range(times - 1):
            self.assertEqual(self.post(f"/jobs/{job_id}/reset?from=script").status_code, 200)
            self.run_step(job_id, "script")
            self.run_step(job_id, "review")

    def stuck_job(self, times=3):
        self.post("/series", SERIES)
        job_id = self.post("/jobs", {"seriesId": "ai-office"}).json()["id"]
        self.fail_review(job_id, times)
        return job_id

    def questions(self):
        return [m for m in self.tg.sent("sendMessage") if "검토" in m["text"] and "reply_markup" in m]


class AskTest(StuckCase):
    def test_three_low_scores_ask_once_with_two_buttons(self):
        job_id = self.stuck_job(3)
        poller = self.app.state.telegram_poller

        poller.remind_due()
        poller.remind_due()

        (q,) = self.questions()
        self.assertIn("1화 배우기", q["text"])
        self.assertIn("구체성 2점", q["text"])
        self.assertEqual([b["callback_data"] for b in q["reply_markup"]["inline_keyboard"][0]], [f"ro:{job_id}", f"rs:{job_id}"])

    def test_two_low_scores_do_not_ask_yet(self):
        self.stuck_job(2)

        self.app.state.telegram_poller.remind_due()

        self.assertEqual(self.questions(), [])


class MixedFailuresTest(StuckCase):
    def test_critical_and_low_score_failures_count_together(self):
        """2026-10-21 실제: 개요를 고친 6화가 점수 미달 2번 + 치명 오류 1번으로 떨어졌는데, 점수 미달만 세서
        질문을 보내지 않았다(생산 워크플로는 세 번으로 보고 멈춤) → 아무 알림 없이 멈춤"""
        self.post("/series", SERIES)
        job_id = self.post("/jobs", {"seriesId": "ai-office"}).json()["id"]
        review = self.steps["review"]
        self.run_until(job_id, "review")  # 점수 미달
        review.fail = StepFailure("deterministic", "검토에서 치명 오류: 3번: 사실과 다르다", retry_from="script")
        self.post(f"/jobs/{job_id}/reset?from=script")
        self.run_step(job_id, "script")
        self.run_step(job_id, "review")  # 치명 오류
        review.fail = StepFailure("deterministic", LOW, retry_from="script")
        self.post(f"/jobs/{job_id}/reset?from=script")
        self.run_step(job_id, "script")
        self.run_step(job_id, "review")  # 점수 미달

        self.app.state.telegram_poller.remind_due()

        (q,) = self.questions()
        self.assertIn(f"ro:{job_id}", str(q["reply_markup"]))

    def test_running_job_with_no_step_shows_as_next_in_line(self):
        job_id = self.stuck_job(3)
        self.app.state.telegram_poller.remind_due()
        self.tg.press(f"ro:{job_id}")
        self.poll()

        text = self.get("/overview").json()["text"]

        self.assertNotIn("( 단계)", text)
        self.assertIn("1화 배우기 — 🟡 만들 차례", text)


class FixOutlineTest(StuckCase):
    def test_fix_rewrites_outline_from_feedback_and_resets_to_topic(self):
        job_id = self.stuck_job(3)
        self.app.state.telegram_poller.remind_due()
        self.tg.press(f"ro:{job_id}")

        self.poll()

        self.assertIn("구체성 2점", self.llm.last_user_text())  # 검토 의견을 넣어 고친다
        ep = self.get("/series/ai-office").json()["episodes"][0]
        self.assertIn("물감 섞기", ep["outline"])
        job = self.get(f"/jobs/{job_id}").json()
        self.assertEqual(job["status"], "RUNNING")
        self.assertEqual(job["events"][-1]["reason"], "reset from=topic")
        self.assertTrue(any((e["reason"] or "").startswith("개요 고침") for e in job["events"]))
        self.assertIn("물감 섞기", self.tg.sent("editMessageText")[-1]["text"])

    def test_after_fix_count_starts_again(self):
        job_id = self.stuck_job(3)
        poller = self.app.state.telegram_poller
        poller.remind_due()
        self.tg.press(f"ro:{job_id}")
        self.poll()
        self.run_until(job_id, "review")  # 고친 뒤 한 번 더 떨어짐

        poller.remind_due()

        self.assertEqual(len(self.questions()), 1)  # 고친 뒤 1번째 실패라 아직 묻지 않는다


class SkipTest(StuckCase):
    def test_skip_marks_episode_and_next_episode_continues_to_done(self):
        job_id = self.stuck_job(3)
        self.app.state.telegram_poller.remind_due()
        self.tg.press(f"rs:{job_id}")
        self.poll()

        self.assertEqual(self.get(f"/jobs/{job_id}").json()["status"], "CANCELLED")
        self.assertEqual(self.get("/series/ai-office").json()["episodes"][0]["status"], "SKIPPED")

        self.steps["review"].fail = None  # 2화는 통과 (실행기가 같은 단계 객체를 쓴다)
        ep2 = self.post("/jobs", {"seriesId": "ai-office"}).json()
        self.assertEqual(ep2["episodeNumber"], 2)
        self.run_until(ep2["id"], "review")
        res = self.post(f"/jobs/{ep2['id']}/approve", {"approvedBy": "운영자"})
        self.assertEqual(res.status_code, 200, res.text)

        self.assertEqual(self.get("/series/ai-office").json()["status"], "DONE")

    def test_skip_shows_in_overview(self):
        job_id = self.stuck_job(3)
        self.app.state.telegram_poller.remind_due()
        self.tg.press(f"rs:{job_id}")
        self.poll()

        self.assertIn("1화 배우기 — ⏭ 건너뜀", self.get("/overview").json()["text"])


class ScriptRuleStuckTest(StuckCase):
    """대본 단계 규칙으로 세 번 떨어져도 같은 질문을 한다 (2026-10-24 실제: 6번째 시리즈 4화가 알림만 오고 멈춤)"""
    review_fails = False

    def make_steps(self):
        steps = super().make_steps()
        steps["script"] = FakeStep("script", ["job.json"], ["script.json"],
                                   fail=StepFailure("deterministic", "대본 규칙을 지키지 못했다: 2번째 문장이 49자다", retry_from="script"))
        return steps

    def test_three_script_rule_failures_ask(self):
        self.post("/series", SERIES)
        job_id = self.post("/jobs", {"seriesId": "ai-office"}).json()["id"]
        self.run_step(job_id, "topic")
        self.run_step(job_id, "script")
        for _ in range(2):
            self.post(f"/jobs/{job_id}/reset?from=script")
            self.run_step(job_id, "script")

        self.app.state.telegram_poller.remind_due()

        (q,) = [m for m in self.tg.sent("sendMessage") if "reply_markup" in m and "ro:" in str(m["reply_markup"])]
        self.assertIn("49자", q["text"])
