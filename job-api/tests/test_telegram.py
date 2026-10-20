"""텔레그램 승인 (아키텍처 D28, 2026-10-16).

job-api 가 검토 대기 알림을 [승인][반려] 버튼과 함께 보내고, getUpdates 로 버튼 응답을 가져와 처리한다.
나가는 연결만 쓴다(MacBook 을 인터넷에 열지 않는다). 실제 텔레그램 대신 httpx.MockTransport.
"""
import json

import httpx

from app.notify.telegram import TelegramBot
from tests.fakes import FakeLlm, FakeRegistry
from fastapi.testclient import TestClient

from app.main import create_app
from tests.helpers import AppTestCase, inline_executor

CHAT = "4242"


class FakeTelegram:
    def __init__(self):
        self.requests = []
        self.updates = []
        self.fail_send = False

    def __call__(self, request):
        method = request.url.path.rsplit("/", 1)[-1]
        raw = request.read()
        # sendVideo 는 multipart 라 원문 그대로 둔다
        body = {"_raw": raw} if "multipart" in request.headers.get("content-type", "") else json.loads(raw or b"{}")
        self.requests.append((method, body))
        if method == "sendMessage" and self.fail_send:
            return httpx.Response(500, json={"ok": False})
        if method == "getUpdates":
            out = [u for u in self.updates if u["update_id"] >= body.get("offset", 0)]
            return httpx.Response(200, json={"ok": True, "result": out})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(self.requests)}})

    def sent(self, method):
        return [b for m, b in self.requests if m == method]

    def say(self, text, chat=CHAT):
        uid = 100 + len(self.updates)
        self.updates.append({"update_id": uid, "message": {
            "message_id": 500 + uid, "from": {"id": int(chat)}, "chat": {"id": int(chat)}, "text": text}})

    def press(self, data, chat=CHAT, update_id=None):
        uid = update_id or 100 + len(self.updates)
        self.updates.append({"update_id": uid, "callback_query": {
            "id": f"cb{uid}", "from": {"id": int(chat)}, "data": data,
            "message": {"message_id": 7, "chat": {"id": int(chat)}}}})


class TelegramCase(AppTestCase):
    def make_telegram(self):
        self.tg = FakeTelegram()
        return TelegramBot("TOKEN-NOT-SECRET", CHAT, http=httpx.Client(transport=httpx.MockTransport(self.tg)))

    def poll(self):
        self.app.state.telegram_poller.poll_once(timeout=0)

    def status(self, job_id):
        return self.get(f"/jobs/{job_id}").json()["status"]


class ReviewMessageTest(TelegramCase):
    def test_review_sends_buttons(self):
        job_id = self.new_job("벡터 데이터베이스란?")

        self.run_until(job_id, "review")

        (msg,) = self.tg.sent("sendMessage")
        self.assertEqual(msg["chat_id"], CHAT)
        self.assertIn("벡터 데이터베이스란?", msg["text"])
        buttons = [b for row in msg["reply_markup"]["inline_keyboard"] for b in row]
        self.assertEqual([(b["text"], b["callback_data"]) for b in buttons],
                         [("승인(공개)", f"a:{job_id}"), ("반려", f"r:{job_id}")])

    def test_telegram_failure_does_not_break_production(self):
        self.tg.fail_send = True
        job_id = self.new_job()

        self.run_until(job_id, "review")

        self.assertEqual(self.status(job_id), "REVIEW")


class ButtonTest(TelegramCase):
    def test_approve_button(self):
        job_id = self.new_job()
        self.run_until(job_id, "review")
        self.tg.press(f"a:{job_id}")

        self.poll()

        self.assertEqual(self.status(job_id), "APPROVED")  # 업로드 없는 파이프라인이라 공개 전환은 건너뜀
        self.assertEqual(self.get(f"/jobs/{job_id}").json()["publication"]["approvedBy"], "텔레그램")
        (ans,) = self.tg.sent("answerCallbackQuery")
        self.assertEqual(ans["callback_query_id"], "cb100")
        (edit,) = self.tg.sent("editMessageText")
        self.assertIn("승인", edit["text"])
        self.assertNotIn("reply_markup", edit)  # 처리한 메시지에서 버튼을 없앤다

    def test_reject_button(self):
        job_id = self.new_job()
        self.run_until(job_id, "review")
        self.tg.press(f"r:{job_id}")

        self.poll()

        job = self.get(f"/jobs/{job_id}").json()
        self.assertEqual(job["status"], "REJECTED")
        self.assertEqual(job["events"][-1]["reason"], "텔레그램에서 반려")

    def test_other_chat_is_ignored(self):
        job_id = self.new_job()
        self.run_until(job_id, "review")
        self.tg.press(f"a:{job_id}", chat="999")

        self.poll()

        self.assertEqual(self.status(job_id), "REVIEW")
        self.assertIn("권한", self.tg.sent("answerCallbackQuery")[0]["text"])

    def test_already_handled_button_says_so(self):
        job_id = self.new_job()
        self.run_until(job_id, "review")
        self.tg.press(f"a:{job_id}")
        self.tg.press(f"a:{job_id}")

        self.poll()

        self.assertIn("REVIEW", self.tg.sent("answerCallbackQuery")[-1]["text"])  # 두 번째는 '검토 대기에서만' 안내만
        self.assertEqual(len(self.tg.sent("editMessageText")), 1)  # 메시지는 첫 처리 결과 그대로

    def test_offset_moves_forward(self):
        job_id = self.new_job()
        self.run_until(job_id, "review")
        self.tg.press(f"a:{job_id}", update_id=500)

        self.poll()
        self.poll()

        offsets = [b.get("offset") for b in self.tg.sent("getUpdates")]
        self.assertEqual(offsets[-1], 501)
        self.assertEqual(len(self.tg.sent("answerCallbackQuery")), 1)  # 같은 응답을 두 번 처리하지 않는다


SERIES = {"key": "ai-office", "category": "ai-it", "title": "민지의 AI 적응기",
          "episodes": [{"number": 1, "title": "배우기", "outline": "a"}, {"number": 2, "title": "판단하기", "outline": "b"}]}


class SeriesOrderTest(TelegramCase):
    def test_out_of_order_approve_explains(self):
        self.post("/series", SERIES)
        ep1 = self.post("/jobs", {"seriesId": "ai-office"}).json()["id"]
        self.run_until(ep1, "review")
        ep2 = self.post("/jobs", {"seriesId": "ai-office"}).json()["id"]
        self.run_until(ep2, "review")
        self.tg.press(f"a:{ep2}")

        self.poll()

        self.assertEqual(self.status(ep2), "REVIEW")
        # 2026-10-19 실제: 순서가 틀려 거절될 때 버튼까지 지워 다시 누를 수 없었다. 안내만 띄우고 메시지·버튼은 둔다
        self.assertIn("1화를 먼저 승인", self.tg.sent("answerCallbackQuery")[-1]["text"])
        self.assertEqual(self.tg.sent("editMessageText"), [])

    def test_after_previous_is_approved_the_same_button_works(self):
        self.post("/series", SERIES)
        ep1 = self.post("/jobs", {"seriesId": "ai-office"}).json()["id"]
        self.run_until(ep1, "review")
        ep2 = self.post("/jobs", {"seriesId": "ai-office"}).json()["id"]
        self.run_until(ep2, "review")
        self.tg.press(f"a:{ep2}", update_id=1)
        self.poll()

        self.tg.press(f"a:{ep1}", update_id=2)
        self.tg.press(f"a:{ep2}", update_id=3)
        self.poll()

        self.assertEqual([self.status(ep1), self.status(ep2)], ["APPROVED", "APPROVED"])
        self.assertIn("2화", self.tg.sent("sendMessage")[-1]["text"])  # 검토 대기 알림에 화 번호
        self.assertIn("1번째 시리즈 '민지의 AI 적응기'", self.tg.sent("sendMessage")[-1]["text"])  # 몇 번째 시리즈 (D33)


PLAN = {"title": "민준의 데이터 탐험", "bible": {"premise": "데이터를 배운다", "tone": "t", "characters": []},
        "episodes": [{"title": "데이터란", "outline": "a"}, {"title": "표와 열", "outline": "b"}]}


class PlanButtonTest(TelegramCase):
    def make_providers(self):
        return FakeRegistry(FakeLlm(PLAN))

    def test_generated_plan_is_sent_and_approved_by_button(self):
        sid = self.post("/series", {"category": "ai-it", "episodeCount": 2}).json()["id"]

        (msg,) = self.tg.sent("sendMessage")
        self.assertIn("민준의 데이터 탐험", msg["text"])
        self.assertIn("1. 데이터란", msg["text"])
        self.assertIn("1번째 시리즈", msg["text"])  # 첫 시리즈 계획 (D33)
        self.assertEqual(msg["reply_markup"]["inline_keyboard"][0][0]["callback_data"], f"p:{sid}")

        self.tg.press(f"p:{sid}")
        self.poll()

        self.assertEqual(self.get(f"/series/{sid}").json()["status"], "APPROVED")


class ChangePlanTest(TelegramCase):
    """계획 메시지의 [다른 주제로]: 그 계획을 취소하고 바로 주제·화 수를 묻는다 (2026-10-21 사용자: 텔레그램 안에서 끝내기)"""

    def setUp(self):
        self.llm = FakeLlm(PLAN, plan(3))
        super().setUp()

    def make_providers(self):
        return FakeRegistry(self.llm)

    def test_plan_message_has_change_button(self):
        sid = self.post("/series", {"category": "ai-it", "episodeCount": 2}).json()["id"]

        (msg,) = self.tg.sent("sendMessage")

        self.assertEqual([b["callback_data"] for b in msg["reply_markup"]["inline_keyboard"][0]], [f"p:{sid}", f"pc:{sid}"])

    def test_change_cancels_plan_and_asks_then_answer_makes_new_plan(self):
        sid = self.post("/series", {"category": "ai-it", "episodeCount": 2}).json()["id"]
        self.tg.press(f"pc:{sid}")
        self.poll()

        self.assertEqual(self.get(f"/series/{sid}").json()["status"], "CANCELLED")
        question = self.tg.sent("sendMessage")[-1]
        self.assertIn("주제", question["text"])
        self.assertEqual([b["callback_data"] for b in question["reply_markup"]["inline_keyboard"][0]], ["q:auto", "q:skip"])

        self.tg.say("도커 입문, 3")
        self.poll()

        proposed = self.get("/series?status=PROPOSED").json()["items"]
        self.assertEqual(len(proposed), 1)
        self.assertIn("도커 입문", self.llm.last_user_text())

    def test_change_on_approved_plan_is_refused_and_button_stays(self):
        sid = self.post("/series", {"category": "ai-it", "episodeCount": 2}).json()["id"]
        self.tg.press(f"p:{sid}")
        self.poll()
        edits = len(self.tg.sent("editMessageText"))
        self.tg.press(f"pc:{sid}")

        self.poll()

        self.assertEqual(self.get(f"/series/{sid}").json()["status"], "APPROVED")
        self.assertIn("승인 대기", self.tg.sent("answerCallbackQuery")[-1]["text"])
        self.assertEqual(len(self.tg.sent("editMessageText")), edits)


class PlanReminderTest(TelegramCase):
    """승인 대기 계획을 하루에 한 번 다시 알린다 (2026-10-20 실제: 10-19 에 한 번 보낸 [계획 승인] 을 놓치자
    주제 질문도 막혀 다음 시리즈가 아무 알림 없이 멈췄다)"""

    def make_providers(self):
        return FakeRegistry(FakeLlm(PLAN))

    def plan_messages(self):
        return [m for m in self.tg.sent("sendMessage") if "계획 승인 필요" in m["text"]]

    def test_waiting_plan_is_sent_again_after_a_day_once(self):
        sid = self.post("/series", {"category": "ai-it", "episodeCount": 2}).json()["id"]
        poller = self.app.state.telegram_poller

        poller.remind_due()
        self.assertEqual(len(self.plan_messages()), 1)  # 하루 안에는 다시 보내지 않는다
        self.clock.advance(hours=24, minutes=1)
        poller.remind_due()
        poller.remind_due()

        msgs = self.plan_messages()
        self.assertEqual(len(msgs), 2)
        self.assertIn("다시 알림", msgs[-1]["text"])
        self.assertEqual(msgs[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"], f"p:{sid}")

    def test_plan_without_sent_record_is_sent_right_away(self):
        self.post("/series", {"category": "ai-it", "episodeCount": 2})
        (self.settings.data_dir / "telegram" / "series_request.json").unlink()  # 보낸 기록이 생기기 전에 만든 계획

        self.app.state.telegram_poller.remind_due()

        self.assertEqual(len(self.plan_messages()), 2)

    def test_approved_plan_is_not_reminded(self):
        sid = self.post("/series", {"category": "ai-it", "episodeCount": 2}).json()["id"]
        self.tg.press(f"p:{sid}")
        self.poll()
        self.clock.advance(days=2)

        self.app.state.telegram_poller.remind_due()

        self.assertEqual(len(self.plan_messages()), 1)


class ReminderTest(TelegramCase):
    """검토 대기가 오래 남으면 다시 알린다 (2026-10-19 사용자). 지금 승인할 수 있는 차례인 것만"""

    def reminders(self):
        return [m for m in self.tg.sent("sendMessage") if "다시 알림" in m["text"]]

    def test_pending_review_is_sent_again_after_six_hours_once(self):
        job_id = self.new_job()
        self.run_until(job_id, "review")
        poller = self.app.state.telegram_poller

        poller.remind_due()
        self.assertEqual(self.reminders(), [])  # 아직 6시간 전
        self.clock.advance(hours=6, minutes=1)
        poller.remind_due()
        poller.remind_due()  # 같은 6시간 안에는 한 번만

        (msg,) = self.reminders()
        self.assertEqual(msg["reply_markup"]["inline_keyboard"][0][0]["callback_data"], f"a:{job_id}")

    def test_episode_waiting_for_previous_is_not_reminded(self):
        self.post("/series", SERIES)
        ep1 = self.post("/jobs", {"seriesId": "ai-office"}).json()["id"]
        self.run_until(ep1, "review")
        ep2 = self.post("/jobs", {"seriesId": "ai-office"}).json()["id"]
        self.run_until(ep2, "review")
        self.clock.advance(hours=7)

        self.app.state.telegram_poller.remind_due()

        self.assertEqual([m["reply_markup"]["inline_keyboard"][0][0]["callback_data"] for m in self.reminders()], [f"a:{ep1}"])


def plan(n, title="쿠버네티스 첫걸음"):
    return {"title": title, "bible": {"premise": "p", "tone": "t"},
            "episodes": [{"title": f"개념 {i}", "outline": "o"} for i in range(1, n + 1)]}


class SeriesRequestTest(TelegramCase):
    """다음 시리즈 계획 전에 텔레그램으로 주제·화 수를 묻는다 (2026-10-19 사용자)"""

    def setUp(self):
        self.llm = FakeLlm()
        super().setUp()

    def make_providers(self):
        return FakeRegistry(self.llm)

    def ask(self):
        return self.post("/series/request", {"category": "ai-it"})

    def proposed(self):
        return self.get("/series?status=PROPOSED").json()["items"]

    def test_question_is_sent_with_auto_and_skip_buttons(self):
        res = self.ask()

        self.assertEqual(res.json()["asked"], True, res.text)
        (msg,) = self.tg.sent("sendMessage")
        self.assertIn("주제", msg["text"])
        self.assertEqual([b["callback_data"] for b in msg["reply_markup"]["inline_keyboard"][0]], ["q:auto", "q:skip"])

    def test_asked_once_a_day(self):
        self.ask()
        again = self.ask()
        self.clock.advance(days=1)
        tomorrow = self.ask()

        self.assertEqual((again.json()["asked"], again.json()["reason"]), (False, "asked_today"))
        self.assertTrue(tomorrow.json()["asked"])
        self.assertEqual(len(self.tg.sent("sendMessage")), 2)

    def test_answer_with_theme_and_count_makes_plan(self):
        self.llm.responses = [plan(4)]
        self.ask()
        self.tg.say("쿠버네티스 기초, 4화")

        self.poll()

        self.assertIn("쿠버네티스 기초", self.llm.last_user_text())
        self.assertEqual(self.llm.requests[-1]["schema"]["properties"]["episodes"]["minItems"], 4)
        (sid,) = [x["id"] for x in self.proposed()]
        self.assertEqual(self.tg.sent("sendMessage")[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"], f"p:{sid}")

    def test_count_defaults_to_ten(self):
        self.llm.responses = [plan(10)]
        self.ask()
        self.tg.say("도커 입문")

        self.poll()

        self.assertEqual(self.llm.requests[-1]["schema"]["properties"]["episodes"]["minItems"], 10)
        self.assertEqual(len(self.proposed()), 1)

    def test_count_out_of_range_is_explained_and_still_waits(self):
        self.ask()
        self.tg.say("도커 입문, 50")
        self.poll()

        self.assertEqual(self.llm.requests, [])
        self.assertIn("3~20", self.tg.sent("sendMessage")[-1]["text"])

        self.llm.responses = [plan(5)]
        self.tg.say("도커 입문, 5")
        self.poll()
        self.assertEqual(len(self.proposed()), 1)

    def test_auto_button_makes_plan_without_theme(self):
        self.llm.responses = [plan(10, "자동 제목")]
        self.ask()
        self.tg.press("q:auto")

        self.poll()

        self.assertNotIn("사용자가 정한 주제", self.llm.last_user_text())
        self.assertEqual([x["title"] for x in self.proposed()], ["자동 제목"])

    def test_skip_button_waits_until_tomorrow(self):
        self.ask()
        self.tg.press("q:skip")
        self.poll()
        self.tg.say("이건 답이 아님")  # 건너뛴 뒤의 글은 답으로 받지 않는다
        self.poll()

        self.assertEqual(self.llm.requests, [])
        self.assertIn("건너", self.tg.sent("editMessageText")[-1]["text"])
        self.assertFalse(self.ask().json()["asked"])
        self.clock.advance(days=1)
        self.assertTrue(self.ask().json()["asked"])

    def test_series_command_works_any_time(self):
        self.llm.responses = [plan(3)]
        self.tg.say("/series 쿠버네티스 기초, 3")

        self.poll()

        self.assertIn("쿠버네티스 기초", self.llm.last_user_text())
        self.assertEqual(len(self.proposed()), 1)

    def test_other_chat_is_ignored(self):
        self.ask()
        self.tg.say("/series 다른 사람, 3", chat="999")
        self.tg.say("다른 사람, 3", chat="999")

        self.poll()

        self.assertEqual(self.llm.requests, [])

    def test_text_without_question_is_not_an_answer(self):
        self.tg.say("안녕")

        self.poll()

        self.assertEqual(self.llm.requests, [])

    def test_not_asked_while_plan_waits_for_approval(self):
        self.llm.responses = [plan(3)]
        self.tg.say("/series 도커 입문, 3")
        self.poll()

        res = self.ask()
        self.tg.say("/series 또 하나, 3")
        self.poll()

        self.assertEqual((res.json()["asked"], res.json()["reason"]), (False, "plan_pending"))
        self.assertEqual(len(self.proposed()), 1)
        self.assertIn("승인 대기", self.tg.sent("sendMessage")[-1]["text"])

    def test_busy_answer_is_kept_and_made_later(self):
        self.llm.responses = [plan(3)]
        self.ask()
        self.tg.say("도커 입문, 3")
        with self.app.state.runner.exclusive("다른 작업"):
            self.poll()
        self.assertEqual(self.proposed(), [])
        self.assertIn("끝나면", self.tg.sent("sendMessage")[-1]["text"])

        self.app.state.telegram_poller.make_wanted_plan()

        self.assertEqual(len(self.proposed()), 1)

    def test_waiting_question_survives_restart(self):
        self.ask()
        self.client.__exit__(None, None, None)  # 서버 재시작
        self.llm.responses = [plan(3)]
        self.app = create_app(self.settings, steps=self.steps, pipeline=self.pipeline, executor=inline_executor,
                              notify=lambda url, payload: None, clock=self.clock, providers=self.make_providers(),
                              telegram=self.make_telegram())
        self.client = TestClient(self.app)
        self.client.__enter__()

        self.tg.say("도커 입문, 3")
        self.poll()

        self.assertEqual(len(self.proposed()), 1)
