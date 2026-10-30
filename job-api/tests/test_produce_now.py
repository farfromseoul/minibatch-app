"""텔레그램 /run 으로 n8n 1번 생산을 바로 시작 (2026-10-31 사용자: 정각을 기다리지 않고).

job-api 가 n8n 1번 워크플로의 웹훅을 부른다. 1번 워크플로가 이미 돌고 있으면(최근 90초 안에 /jobs/next·단계·되돌리기 요청,
또는 단계 실행 중) 부르지 않고 알린다. n8n 은 가짜 함수로 대신한다.
"""
import httpx

from tests.helpers import FakeStep
from tests.test_telegram import TelegramCase


class ProduceCase(TelegramCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        self.fail = None

        def post(url, timeout):
            self.calls.append(url)
            if self.fail:
                raise self.fail
            return httpx.Response(200, json={"message": "Workflow was started"})
        self.app.state.production.post = post

    def last(self):
        return self.tg.sent("sendMessage")[-1]["text"]

    def run_cmd(self):
        self.tg.say("/run")
        self.poll()
        return self.last()


class RunCommandTest(ProduceCase):
    def test_run_calls_produce_webhook(self):
        msg = self.run_cmd()

        self.assertEqual(self.calls, ["http://n8n:5678/webhook/minibatch-produce-now"])
        self.assertIn("▶", msg)

    def test_recent_production_activity_blocks_second_run(self):
        self.get("/jobs/next")  # 1번 워크플로가 다녀감

        msg = self.run_cmd()

        self.assertEqual(self.calls, [])
        self.assertIn("이미 생산 중", msg)

    def test_activity_older_than_window_allows_run(self):
        self.get("/jobs/next")
        self.clock.advance(seconds=120)

        self.run_cmd()

        self.assertEqual(len(self.calls), 1)

    def test_run_twice_in_a_row_calls_once(self):
        self.run_cmd()
        msg = self.run_cmd()

        self.assertEqual(len(self.calls), 1)
        self.assertIn("이미 생산 중", msg)

    def test_n8n_failure_is_reported(self):
        self.fail = httpx.ConnectError("n8n 꺼짐")

        msg = self.run_cmd()

        self.assertIn("n8n", msg)
        self.assertIn("⚠️", msg)

    def test_api_route_does_the_same(self):
        res = self.post("/produce/run")

        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()["started"])
        res = self.post("/produce/run")
        self.assertFalse(res.json()["started"])

    def test_help_lists_run(self):
        self.tg.say("/help")
        self.poll()
        self.assertIn("/run", self.last())


class RunningStepBlocksTest(ProduceCase):
    def make_steps(self):
        self.gate = __import__("threading").Event()
        return {"script": FakeStep("script", ["job.json"], ["script.json"], block=self.gate),
                "review": FakeStep("review", ["script.json"], ["review.json"])}

    def test_step_running_blocks_run(self):
        st = self.app.state.production
        st.runner_busy = lambda: "short-x script"  # 단계 실행 중
        self.clock.advance(seconds=600)

        msg = self.run_cmd()

        self.assertEqual(self.calls, [])
        self.assertIn("short-x script", msg)
