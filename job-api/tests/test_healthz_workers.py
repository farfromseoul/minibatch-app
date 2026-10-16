"""/healthz 작업자·토큰 확인 (아키텍처 "인터페이스": DB, LLM 서버, tts-worker, render-worker, 디스크).

작업자가 죽어도 job-api 자체는 살아 있으므로 200 을 주고 경고만 단다. n8n 이 5분마다 보고 경고를 알린다.
"""
import json
import socket
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

from tests.fakes import FakeLlm, FakeRegistry
from tests.helpers import AppTestCase


def closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Ok(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = json.dumps({"status": "ok", "data": []}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class Registry(FakeRegistry):
    def __init__(self, tts_url, llm_url):
        super().__init__(FakeLlm(), tts_url=tts_url)
        self.config = {"llm": {"steps": {"script": "lmstudio"},
                               "providers": {"lmstudio": {"kind": "openai-compatible", "base_url": llm_url}}}}


class WorkersUpTest(AppTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Ok)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def extra_settings(self):
        return {"render_worker_url": self.url}

    def make_providers(self):
        return Registry(self.url, self.url + "/v1")

    def write_token(self, created_at):
        self.settings.youtube_token_file.parent.mkdir(parents=True, exist_ok=True)
        self.settings.youtube_token_file.write_text(json.dumps({"refresh_token": "x", "created_at": created_at}))

    def test_all_reachable(self):
        self.write_token((self.clock.now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))

        body = self.client.get("/healthz").json()

        self.assertEqual(body["status"], "ok")
        for name in ("llm", "tts", "render", "youtube_token"):
            self.assertTrue(body["checks"][name], name)
        self.assertEqual(body["warnings"], [])

    def test_old_youtube_token_warns_before_7_day_expiry(self):
        # 동의 화면이 테스트 상태면 갱신 토큰은 7일 뒤 만료된다 (실행계획 15번, R20)
        self.write_token((self.clock.now - timedelta(days=6, hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))

        body = self.client.get("/healthz").json()

        self.assertTrue(any("갱신 토큰" in w and "6일" in w for w in body["warnings"]), body["warnings"])

    def test_missing_youtube_token_warns(self):
        body = self.client.get("/healthz").json()

        self.assertFalse(body["checks"]["youtube_token"])
        self.assertTrue(any("15번" in w for w in body["warnings"]))


class WorkersDownTest(AppTestCase):
    def extra_settings(self):
        return {"render_worker_url": f"http://127.0.0.1:{closed_port()}"}

    def make_providers(self):
        port = closed_port()
        return Registry(f"http://127.0.0.1:{port}", f"http://127.0.0.1:{port}/v1")

    def test_down_workers_are_warnings_not_errors(self):
        res = self.client.get("/healthz")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "ok")  # job-api 자체(DB)는 정상
        self.assertEqual((body["checks"]["llm"], body["checks"]["tts"], body["checks"]["render"]), (False, False, False))
        for word in ("LLM", "tts-worker", "render-worker"):
            self.assertTrue(any(word in w for w in body["warnings"]), word)
