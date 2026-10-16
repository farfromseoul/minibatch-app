"""텔레그램 승인 (아키텍처 D28, 2026-10-16).

job-api 가 검토 대기 알림을 [승인][반려] 버튼과 함께 보내고, getUpdates 로 버튼 응답을 가져와 처리한다.
나가는 연결만 쓴다(MacBook 을 인터넷에 열지 않는다). 실제 텔레그램 대신 httpx.MockTransport.
"""
import json

import httpx

from app.notify.telegram import TelegramBot
from tests.fakes import FakeLlm, FakeRegistry
from tests.helpers import AppTestCase

CHAT = "4242"


class FakeTelegram:
    def __init__(self):
        self.requests = []
        self.updates = []
        self.fail_send = False

    def __call__(self, request):
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content or b"{}")
        self.requests.append((method, body))
        if method == "sendMessage" and self.fail_send:
            return httpx.Response(500, json={"ok": False})
        if method == "getUpdates":
            out = [u for u in self.updates if u["update_id"] >= body.get("offset", 0)]
            return httpx.Response(200, json={"ok": True, "result": out})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(self.requests)}})

    def sent(self, method):
        return [b for m, b in self.requests if m == method]

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

        self.assertIn("REVIEW", self.tg.sent("editMessageText")[-1]["text"])  # 두 번째는 '검토 대기에서만' 안내

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
        self.assertIn("1화를 먼저 승인", self.tg.sent("editMessageText")[-1]["text"])
        self.assertIn("2화", self.tg.sent("sendMessage")[-1]["text"])  # 검토 대기 알림에 화 번호


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
        self.assertEqual(msg["reply_markup"]["inline_keyboard"][0][0]["callback_data"], f"p:{sid}")

        self.tg.press(f"p:{sid}")
        self.poll()

        self.assertEqual(self.get(f"/series/{sid}").json()["status"], "APPROVED")
