"""providers.yaml 읽기(D19)와 openai-compatible 어댑터 계약 테스트.

가짜 LM Studio(HTTP 서버)로 응답 모양을 바꿔 가며 시험한다. 나중에 claude-api 구현도 같은 계약을 통과해야 한다.
"""
import json
import pathlib
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.llm.base import LlmError
from app.providers import ProviderError, load_providers

PROVIDERS = """
llm:
  steps: {script: local, review: local, scenes: local}
  providers:
    local:
      kind: openai-compatible
      base_url: http://127.0.0.1:PORT/v1
      model: qwen/qwen3.8-27b
      structured_output: json_schema
      extra_body: {ttl: 120}
      timeout_sec: 2
tts:
  provider: main
  providers:
    main: {kind: http-worker, url: "http://tts-worker:8090", engine: supertonic, voice: M1, sample_rate: 44100, chars_per_sec: 5.6}
video:
  clip_engine: none
"""


class FakeLmStudio(BaseHTTPRequestHandler):
    reply = {}
    status = 200
    delay = 0.0
    received = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeLmStudio.received.append((self.path, body))
        if FakeLmStudio.delay:
            threading.Event().wait(FakeLmStudio.delay)
        payload = json.dumps(FakeLmStudio.reply).encode()
        self.send_response(FakeLmStudio.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def chat_reply(content="", reasoning=None, tokens=(11, 22)):
    msg = {"role": "assistant", "content": content}
    if reasoning is not None:
        msg["reasoning_content"] = reasoning
    return {"model": "qwen/qwen3.8-27b", "choices": [{"message": msg}],
            "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]}}


class ProvidersTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, text):
        p = self.dir / "providers.yaml"
        p.write_text(text)
        return p

    def test_loads_steps_and_tts_settings(self):
        reg = load_providers(self.write(PROVIDERS.replace("PORT", "1234")))

        self.assertEqual(reg.llm("script").name, "openai-compatible")
        self.assertAlmostEqual(reg.chars_per_sec, 5.6)
        self.assertEqual(reg.tts_settings()["url"], "http://tts-worker:8090")

    def test_unknown_kind_fails_at_start(self):
        with self.assertRaises(ProviderError):
            load_providers(self.write(PROVIDERS.replace("openai-compatible", "mystery")))

    def test_step_pointing_to_missing_provider_fails(self):
        with self.assertRaises(ProviderError):
            load_providers(self.write(PROVIDERS.replace("script: local", "script: claude")))

    def test_api_key_file_is_checked_only_when_selected(self):
        unused = PROVIDERS.replace("    local:", "    claude:\n      kind: claude-api\n      model: x\n"
                                   "      api_key_file: /nope/key\n    local:")
        load_providers(self.write(unused.replace("PORT", "1")))  # claude 를 안 쓰면 키가 없어도 된다

        with self.assertRaises(ProviderError):
            load_providers(self.write(unused.replace("script: local", "script: claude")))


class OpenAiCompatibleContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeLmStudio)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeLmStudio.status, FakeLmStudio.delay, FakeLmStudio.received = 200, 0.0, []
        self._tmp = tempfile.TemporaryDirectory()
        p = pathlib.Path(self._tmp.name) / "providers.yaml"
        p.write_text(PROVIDERS.replace("PORT", str(self.port)))
        self.llm = load_providers(p).llm("script")

    def tearDown(self):
        self._tmp.cleanup()

    def call(self):
        return self.llm.generate_json([{"role": "user", "content": "대본"}], {"type": "object"}, "script")

    def test_request_has_schema_model_and_extra_body(self):
        FakeLmStudio.reply = chat_reply('{"a": 1}')

        self.call()

        path, body = FakeLmStudio.received[-1]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(body["model"], "qwen/qwen3.8-27b")
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertEqual(body["response_format"]["json_schema"]["name"], "script")
        self.assertEqual(body["ttl"], 120)

    def test_reads_content_and_tokens(self):
        FakeLmStudio.reply = chat_reply('{"a": 1}', tokens=(5, 7))

        r = self.call()

        self.assertEqual((r.data, r.source, r.input_tokens, r.output_tokens, r.model), ({"a": 1}, "content", 5, 7, "qwen/qwen3.8-27b"))

    def test_falls_back_to_reasoning_content(self):
        FakeLmStudio.reply = chat_reply("", reasoning='{"a": 2}')

        r = self.call()

        self.assertEqual((r.data, r.source), ({"a": 2}, "reasoning_content"))

    def test_strips_think_block_and_code_fence(self):
        FakeLmStudio.reply = chat_reply('<think>생각</think>\n```json\n{"a": 3}\n```')

        self.assertEqual(self.call().data, {"a": 3})

    def test_non_json_answer_is_invalid_output(self):
        FakeLmStudio.reply = chat_reply("죄송합니다")

        with self.assertRaises(LlmError) as ctx:
            self.call()
        self.assertEqual(ctx.exception.kind, "invalid_output")

    def test_server_error_and_timeout_are_transient(self):
        FakeLmStudio.reply, FakeLmStudio.status = {"error": "x"}, 500
        with self.assertRaises(LlmError) as e1:
            self.call()
        FakeLmStudio.status, FakeLmStudio.delay = 200, 3.0  # 제공자 timeout_sec 2
        FakeLmStudio.reply = chat_reply('{"a": 1}')
        with self.assertRaises(LlmError) as e2:
            self.call()

        self.assertEqual((e1.exception.kind, e2.exception.kind), ("transient", "transient"))

    def test_unreachable_server_is_transient(self):
        self.llm.base_url = "http://127.0.0.1:1/v1"

        with self.assertRaises(LlmError) as ctx:
            self.call()
        self.assertEqual(ctx.exception.kind, "transient")


if __name__ == "__main__":
    unittest.main()
