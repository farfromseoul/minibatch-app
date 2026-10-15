import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from llm_compare.client import chat


class _FakeServer(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FakeServer.received.append((self.path, body))
        reply = {
            "choices": [{"message": {"content": "", "reasoning_content": '{"ok": true}'}}],
            "usage": {"completion_tokens": 7},
        }
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class ChatTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _FakeServer)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}/v1"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        _FakeServer.received.clear()

    def test_sends_schema_and_extra_fields_to_chat_completions(self):
        chat(self.base_url, "m1", [{"role": "user", "content": "hi"}], schema={"type": "object"}, extra={"ttl": 120})

        path, body = _FakeServer.received[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(body["model"], "m1")
        self.assertEqual(body["ttl"], 120)
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertEqual(body["response_format"]["json_schema"]["schema"], {"type": "object"})

    def test_returns_message_tokens_and_elapsed_time(self):
        reply = chat(self.base_url, "m1", [{"role": "user", "content": "hi"}])

        self.assertEqual(reply["message"]["reasoning_content"], '{"ok": true}')
        self.assertEqual(reply["completion_tokens"], 7)
        self.assertGreaterEqual(reply["elapsed_sec"], 0.0)


if __name__ == "__main__":
    unittest.main()
