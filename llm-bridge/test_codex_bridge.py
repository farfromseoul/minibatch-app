"""Codex 중계기 (아키텍처 D32, 2026-10-18).

job-api 의 OpenAI 호환 요청을 받아 `codex exec`(ChatGPT 로그인)로 답한다. 실패하면 로컬 LLM 으로 넘긴다.
codex 는 가짜 실행 파일로, 로컬 LLM 은 가짜 HTTP 서버로 바꾼다. python3 -m unittest test_codex_bridge
"""
import json
import os
import stat
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import codex_bridge

SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}, "meta": {"type": "object", "properties": {"n": {"type": "integer"}}}},
          "required": ["title"]}
BODY = {"model": "codex", "messages": [{"role": "system", "content": "너는 대본 작가다."}, {"role": "user", "content": "RAG 대본"}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "script", "strict": True, "schema": SCHEMA}},
        "temperature": 0.3, "ttl": 120}


def fake_codex(dirpath, *, answer=None, stderr="", code=0):
    """받은 인자·stdin 을 기록하고 -o 파일에 답을 쓰는 가짜 codex"""
    p = Path(dirpath) / "codex"
    p.write_text(f"""#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
stdin = sys.stdin.read()
schema_path = args[args.index("--output-schema") + 1]
json.dump({{"args": args, "stdin": stdin, "schema": json.load(open(schema_path))}}, open({str(Path(dirpath) / 'call.json')!r}, "w"), ensure_ascii=False)
answer = {answer!r}
if answer is not None:
    open(args[args.index("-o") + 1], "w").write(answer)
sys.stderr.write({stderr!r})
sys.exit({code})
""")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


class FakeLocalLlm(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeLocalLlm.calls.append(body)
        out = json.dumps({"model": body["model"], "choices": [{"message": {"role": "assistant", "content": '{"title": "로컬"}'}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


class BridgeCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        FakeLocalLlm.calls = []
        self.local = HTTPServer(("127.0.0.1", 0), FakeLocalLlm)
        threading.Thread(target=self.local.serve_forever, daemon=True).start()

    def tearDown(self):
        self.local.shutdown()
        self._tmp.cleanup()

    def bridge(self, codex, **kw):
        cfg = codex_bridge.Config(codex_bin=str(codex), fallback_url=f"http://127.0.0.1:{self.local.server_port}/v1",
                                  fallback_model="qwen/qwen3.8-27b", timeout_sec=10, **kw)
        return codex_bridge.Bridge(cfg)

    def call(self):
        return json.loads(json.loads(json.dumps(self.res))["choices"][0]["message"]["content"])

    def recorded(self):
        return json.loads((self.dir / "call.json").read_text())


class CodexAnswerTest(BridgeCase):
    def test_answer_comes_from_codex_with_schema_and_prompt(self):
        b = self.bridge(fake_codex(self.dir, answer='{"title": "RAG 60초"}'))

        self.res = b.chat(BODY)

        self.assertEqual(self.call(), {"title": "RAG 60초"})
        self.assertEqual(self.res["model"], "codex")
        rec = self.recorded()
        self.assertIn("exec", rec["args"])
        for flag in ("--ephemeral", "--skip-git-repo-check", "--output-schema", "-o"):
            self.assertIn(flag, rec["args"])
        self.assertEqual(rec["args"][rec["args"].index("-s") + 1], "read-only")  # 명령·파일 쓰기 금지
        self.assertIn("너는 대본 작가다.", rec["stdin"])
        self.assertIn("RAG 대본", rec["stdin"])
        self.assertEqual(FakeLocalLlm.calls, [])

    def test_schema_is_made_strict_for_codex(self):
        b = self.bridge(fake_codex(self.dir, answer='{"title": "x", "meta": {"n": 1}}'))

        b.chat(BODY)

        s = self.recorded()["schema"]
        self.assertEqual((s["additionalProperties"], s["required"]), (False, ["title", "meta"]))
        self.assertEqual((s["properties"]["meta"]["additionalProperties"], s["properties"]["meta"]["required"]), (False, ["n"]))

    def test_model_option_is_passed_when_configured(self):
        b = self.bridge(fake_codex(self.dir, answer='{"title": "x"}'), codex_model="gpt-5.5")

        b.chat(BODY)

        args = self.recorded()["args"]
        self.assertEqual(args[args.index("-m") + 1], "gpt-5.5")


FREE = {"type": "object", "properties": {"scenes": {"type": "array", "items": {"type": "object", "properties": {
    "component": {"type": "string"}, "props": {"type": "object"}}, "required": ["component", "props"]}}}, "required": ["scenes"]}


class FreeObjectTest(BridgeCase):
    """2026-10-19 실제: 장면 props 처럼 속성이 정해지지 않은 객체는 Codex 엄격 형식이 거절한다(invalid_json_schema).
    Codex 에는 JSON 문자열로 받게 하고, 답에서 다시 객체로 푼다"""

    def body(self):
        return dict(BODY, response_format={"type": "json_schema", "json_schema": {"name": "scenes", "schema": FREE}})

    def test_free_object_is_sent_as_json_string(self):
        b = self.bridge(fake_codex(self.dir, answer='{"scenes": [{"component": "TitleReveal", "props": "{\\"title\\": \\"RAG\\"}"}]}'))

        b.chat(self.body())

        props = self.recorded()["schema"]["properties"]["scenes"]["items"]["properties"]["props"]
        self.assertEqual(props["type"], "string")
        self.assertIn("JSON", props["description"])

    def test_json_string_is_turned_back_into_object(self):
        b = self.bridge(fake_codex(self.dir, answer='{"scenes": [{"component": "TitleReveal", "props": "{\\"title\\": \\"RAG\\"}"}]}'))

        self.res = b.chat(self.body())

        self.assertEqual(self.call(), {"scenes": [{"component": "TitleReveal", "props": {"title": "RAG"}}]})
        self.assertEqual(self.res["model"], "codex")

    def test_bad_json_string_falls_back(self):
        b = self.bridge(fake_codex(self.dir, answer='{"scenes": [{"component": "TitleReveal", "props": "제목"}]}'))

        self.res = b.chat(self.body())

        self.assertEqual(self.res["model"], "fallback:qwen/qwen3.8-27b")
        self.assertEqual(b.last_fallback_reason, "invalid_output")


class EffortTest(BridgeCase):
    """Codex 사용량 줄이기 (2026-10-19): 규칙대로 고르는 일(장면·검색어)은 추론을 낮게, 대본은 기본"""

    def body(self, name):
        return dict(BODY, response_format={"type": "json_schema", "json_schema": {"name": name, "schema": SCHEMA}})

    def test_effort_is_set_per_schema_name(self):
        b = self.bridge(fake_codex(self.dir, answer='{"title": "x"}'), effort={"scenes": "low"})

        b.chat(self.body("scenes"))

        args = self.recorded()["args"]
        self.assertEqual(args[args.index("-c") + 1], 'model_reasoning_effort="low"')

    def test_no_effort_option_for_other_steps(self):
        b = self.bridge(fake_codex(self.dir, answer='{"title": "x"}'), effort={"scenes": "low"})

        b.chat(self.body("script"))

        self.assertNotIn("-c", self.recorded()["args"])

    def test_effort_map_is_read_from_env(self):
        os.environ["CODEX_EFFORT"] = "scenes=low, visual_queries=low ,script=medium"
        try:
            cfg = codex_bridge.Config.from_env()
        finally:
            del os.environ["CODEX_EFFORT"]
        self.assertEqual(cfg.effort, {"scenes": "low", "visual_queries": "low", "script": "medium"})


class FallbackTest(BridgeCase):
    def test_usage_limit_falls_back_to_local_llm(self):
        b = self.bridge(fake_codex(self.dir, stderr="ERROR: You've hit your usage limit.", code=1))

        self.res = b.chat(BODY)

        self.assertEqual(self.call(), {"title": "로컬"})
        self.assertEqual(self.res["model"], "fallback:qwen/qwen3.8-27b")
        sent = FakeLocalLlm.calls[0]
        self.assertEqual((sent["model"], sent["ttl"]), ("qwen/qwen3.8-27b", 120))  # 원래 요청 그대로, 모델만 바꿈
        self.assertEqual(b.last_fallback_reason, "usage_limit")

    def test_empty_or_broken_answer_falls_back(self):
        b = self.bridge(fake_codex(self.dir, answer="죄송합니다"))

        self.res = b.chat(BODY)

        self.assertEqual(self.call(), {"title": "로컬"})
        self.assertEqual(b.last_fallback_reason, "invalid_output")

    def test_without_fallback_error_is_reported_as_429(self):
        cfg = codex_bridge.Config(codex_bin=str(fake_codex(self.dir, stderr="usage limit", code=1)), fallback_url="", timeout_sec=10)

        with self.assertRaises(codex_bridge.BridgeError) as cm:
            codex_bridge.Bridge(cfg).chat(BODY)
        self.assertEqual(cm.exception.status, 429)  # job-api 는 429 를 일시적 실패로 보고 다시 시도한다


class HttpTest(BridgeCase):
    def test_http_endpoint_and_models(self):
        b = self.bridge(fake_codex(self.dir, answer='{"title": "http"}'))
        server = codex_bridge.make_server(b, "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            req = urllib.request.Request(f"{base}/v1/chat/completions", json.dumps(BODY).encode(), {"Content-Type": "application/json"})
            res = json.load(urllib.request.urlopen(req, timeout=10))
            models = json.load(urllib.request.urlopen(f"{base}/v1/models", timeout=10))
            health = json.load(urllib.request.urlopen(f"{base}/healthz", timeout=10))
        finally:
            server.shutdown()
        self.assertEqual(json.loads(res["choices"][0]["message"]["content"]), {"title": "http"})
        self.assertEqual(models["data"][0]["id"], "codex")
        self.assertEqual(health["status"], "ok")

    def test_api_key_variable_is_removed_for_codex(self):
        os.environ["OPENAI_API_KEY"] = "sk-test-not-secret"
        try:
            env = codex_bridge.codex_env()
        finally:
            del os.environ["OPENAI_API_KEY"]
        self.assertNotIn("OPENAI_API_KEY", env)  # 있으면 ChatGPT 요금제 대신 API 종량 과금이 될 수 있다


if __name__ == "__main__":
    unittest.main()
