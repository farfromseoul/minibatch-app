"""Codex 중계기: OpenAI 호환 /v1/chat/completions 를 `codex exec`(ChatGPT 로그인)로 답한다 (아키텍처 D32, 2026-10-18).

job-api 는 LM Studio 를 부르던 그대로 이 주소를 부른다(providers.yaml 의 제공자만 바꿈 → 되돌리기도 한 줄).
- 맥 위에서 돈다: ChatGPT 로그인 정보(~/.codex)가 맥에 있다. 컨테이너가 아니다.
- 표준 라이브러리만 쓴다(맥 기본 python3, 3.9).
- codex 가 실패하면(사용량 한도, 오류, JSON 아님) 원래 요청을 그대로 로컬 LLM 에 넘긴다. 대체 주소가 없으면 429(일시적 실패).
- 한 번에 하나만 (구독 한도, 맥 메모리).
- OPENAI_API_KEY 를 지운 환경으로 codex 를 실행한다: 있으면 요금제가 아니라 API 종량 과금이 될 수 있다.

실행: python3 codex_bridge.py  (환경 변수는 Config.from_env 참고)
"""
from __future__ import annotations

import copy
import json
import logging
import os
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

log = logging.getLogger("codex-bridge")

INSTRUCTION = ("도구, 셸 명령, 파일 읽기·쓰기를 하지 말고, 아래 지시와 요청에 대한 최종 답만 "
               "주어진 JSON 스키마 형식으로 하라.")


@dataclass
class Config:
    codex_bin: str = "codex"
    codex_model: str = ""          # 비우면 codex 설정의 기본 모델
    fallback_url: str = ""         # 예: http://127.0.0.1:1234/v1 (LM Studio). 비우면 대체 없음
    fallback_model: str = ""
    timeout_sec: float = 600       # codex 한 번 (정상 10~35초. 2026-10-26: 600 은 멈췄을 때 뒤 요청을 너무 오래 막았다 → 템플릿 180)
    fallback_timeout_sec: float = 600  # 로컬 LLM 은 느리므로 codex 와 따로
    # 요청 스키마 이름(script, scenes, visual_queries …) → Codex 추론 강도(low|medium|high).
    # 규칙대로 고르는 일은 low 로 사용량을 줄인다 (2026-10-19). 없는 이름은 Codex 기본값
    effort: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, env=None) -> "Config":
        e = os.environ if env is None else env
        return cls(codex_bin=e.get("CODEX_BIN", "codex"), codex_model=e.get("CODEX_MODEL", ""),
                   fallback_url=e.get("FALLBACK_URL", ""), fallback_model=e.get("FALLBACK_MODEL", ""),
                   timeout_sec=float(e.get("CODEX_TIMEOUT_SEC", "600")),
                   fallback_timeout_sec=float(e.get("FALLBACK_TIMEOUT_SEC", "600")),
                   effort=_parse_effort(e.get("CODEX_EFFORT", "")))


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _parse_effort(text: str) -> dict:
    """'scenes=low,visual_queries=low' → {'scenes': 'low', 'visual_queries': 'low'}"""
    out = {}
    for part in text.split(","):
        if "=" in part:
            k, v = (x.strip() for x in part.split("=", 1))
            if k and v:
                out[k] = v
    return out


class BridgeError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


FREE_OBJECT_AS_STRING = {"type": "string", "description": "JSON 객체를 문자열로 쓴다 (예: {\"title\": \"...\"})"}


def _free_object(node: Any) -> bool:
    """속성이 정해지지 않은 객체 (장면 props 처럼 템플릿마다 모양이 다른 것)"""
    return isinstance(node, dict) and node.get("type") == "object" and not node.get("properties")


def strict_schema(schema: Any) -> Any:
    """OpenAI 엄격 구조화 출력 규칙: 모든 객체에 additionalProperties false, required = 모든 속성.
    속성이 정해지지 않은 객체는 엄격 형식이 받지 않아(invalid_json_schema, 2026-10-19 장면 props) JSON 문자열로 바꾼다.
    답을 받으면 decode_free_objects 가 다시 객체로 푼다"""

    def walk(node: Any) -> Any:
        if _free_object(node):
            return dict(FREE_OBJECT_AS_STRING)
        if isinstance(node, dict):
            out = {k: walk(v) for k, v in node.items()}
            if out.get("type") == "object" and isinstance(out.get("properties"), dict):
                out["additionalProperties"] = False
                out["required"] = list(out["properties"])
            return out
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(copy.deepcopy(schema))


def decode_free_objects(schema: Any, data: Any) -> Any:
    """strict_schema 가 문자열로 바꾼 자리의 값을 원래 스키마를 따라 객체로 푼다. 객체가 아니면 ValueError"""
    if _free_object(schema):
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict):
            raise ValueError("JSON 객체가 아니다")
        return data
    if isinstance(schema, dict):
        if isinstance(data, dict) and isinstance(schema.get("properties"), dict):
            return {k: decode_free_objects(schema["properties"].get(k), v) for k, v in data.items()}
        if isinstance(data, list) and isinstance(schema.get("items"), dict):
            return [decode_free_objects(schema["items"], v) for v in data]
    return data


def codex_env() -> dict:
    env = dict(os.environ)
    for k in ("OPENAI_API_KEY", "CODEX_API_KEY"):
        env.pop(k, None)
    return env


def _prompt(messages: list) -> str:
    parts = [INSTRUCTION]
    for m in messages:
        role = {"system": "지시", "user": "요청", "assistant": "앞선 답"}.get(m.get("role"), m.get("role"))
        parts.append(f"[{role}]\n{m.get('content', '')}")
    return "\n\n".join(parts)


def _classify(stderr: str) -> str:
    low = stderr.lower()
    if "usage limit" in low or "rate limit" in low:
        return "usage_limit"
    if "log in" in low or "login" in low or "unauthorized" in low:
        return "not_logged_in"
    return "codex_error"


class Bridge:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._lock = threading.Lock()  # 같은 ChatGPT 계정으로 codex 를 동시에 여러 번 돌리지 않는다
        self.last_fallback_reason: Optional[str] = None
        # 연속 실패 (2026-10-26: codex 가 이틀 넘게 멈췄는데 아무 경고가 없었다 → job-api /healthz 가 읽어 경고)
        self.consecutive_failures = 0
        self.last_success_at: Optional[str] = None
        self.last_failure_at: Optional[str] = None
        self.last_error: Optional[str] = None

    def health(self) -> dict:
        return {"status": "ok", "lastFallbackReason": self.last_fallback_reason,
                "consecutiveFailures": self.consecutive_failures, "lastSuccessAt": self.last_success_at,
                "lastFailureAt": self.last_failure_at, "lastError": self.last_error}

    def chat(self, body: dict) -> dict:
        with self._lock:
            try:
                res = self._codex(body)
            except BridgeError as e:
                self.consecutive_failures += 1
                self.last_failure_at, self.last_error = _now(), e.message[:300]
                if not self.cfg.fallback_url:
                    raise
                log.warning("codex 실패(%s) → 로컬 LLM 으로 (연속 %d번)", e.message[:200], self.consecutive_failures)
                self.last_fallback_reason = e.message.split(":", 1)[0]
                return self._fallback(body)
            self.consecutive_failures, self.last_success_at = 0, _now()
            return res

    def _codex(self, body: dict) -> dict:
        rf = body.get("response_format") or {}
        schema = (rf.get("json_schema") or {}).get("schema") or {"type": "object"}
        effort = self.cfg.effort.get((rf.get("json_schema") or {}).get("name", ""))
        with tempfile.TemporaryDirectory(prefix="codex-bridge-") as tmp:
            schema_path, out_path, work = (os.path.join(tmp, n) for n in ("schema.json", "answer.json", "work"))
            os.mkdir(work)
            with open(schema_path, "w", encoding="utf-8") as f:
                json.dump(strict_schema(schema), f, ensure_ascii=False)
            cmd = [self.cfg.codex_bin, "exec", "--ephemeral", "--skip-git-repo-check", "-s", "read-only",
                   "-C", work, "--color", "never", "--output-schema", schema_path, "-o", out_path]
            if self.cfg.codex_model:
                cmd += ["-m", self.cfg.codex_model]
            if effort:
                cmd += ["-c", f'model_reasoning_effort="{effort}"']
            cmd.append("-")
            started = time.time()
            try:
                p = subprocess.run(cmd, input=_prompt(body.get("messages") or []), capture_output=True, text=True,
                                   timeout=self.cfg.timeout_sec, env=codex_env())
            except subprocess.TimeoutExpired:
                raise BridgeError(429, f"timeout: codex {self.cfg.timeout_sec}초 초과")
            if p.returncode != 0:
                tail = (p.stderr or p.stdout or "")[-500:]
                raise BridgeError(429, f"{_classify(tail)}: {tail.strip()}")
            try:
                with open(out_path, encoding="utf-8") as f:
                    text = f.read().strip()
                text = json.dumps(decode_free_objects(schema, json.loads(text)), ensure_ascii=False)
            except (OSError, ValueError):
                raise BridgeError(429, "invalid_output: codex 답이 JSON 이 아니다")
        log.info("codex 답 %.1f초 (%s, 추론 %s)", time.time() - started,
                 (rf.get("json_schema") or {}).get("name", "-"), effort or "기본")
        self.last_fallback_reason = None
        return {"id": f"codex-{int(started)}", "object": "chat.completion", "model": "codex",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
                "usage": {}}

    def _fallback(self, body: dict) -> dict:
        fb = dict(body)
        fb["model"] = self.cfg.fallback_model or body.get("model")
        req = urllib.request.Request(self.cfg.fallback_url.rstrip("/") + "/chat/completions",
                                     json.dumps(fb).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.fallback_timeout_sec) as r:
                res = json.load(r)
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise BridgeError(429, f"fallback_failed: {type(e).__name__}")
        res["model"] = f"fallback:{fb['model']}"
        return res


def make_server(bridge: Bridge, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, obj: dict) -> None:
            data = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.rstrip("/") == "/v1/models":
                return self._send(200, {"object": "list", "data": [{"id": "codex", "object": "model"}]})
            if self.path.rstrip("/") == "/healthz":
                return self._send(200, bridge.health())
            self._send(404, {"error": {"message": "없는 주소"}})

        def do_POST(self):
            if self.path.rstrip("/") != "/v1/chat/completions":
                return self._send(404, {"error": {"message": "없는 주소"}})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                self._send(200, bridge.chat(body))
            except BridgeError as e:
                self._send(e.status, {"error": {"message": e.message}})
            except ValueError:
                self._send(400, {"error": {"message": "JSON 본문이 아니다"}})

        def log_message(self, fmt, *args):
            log.info("%s %s", self.address_string(), fmt % args)

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host, port = os.environ.get("BRIDGE_HOST", "127.0.0.1"), int(os.environ.get("BRIDGE_PORT", "1235"))
    cfg = Config.from_env()
    log.info("codex 중계기 %s:%d, codex=%s, 대체=%s, 추론 강도=%s", host, port, cfg.codex_bin, cfg.fallback_url or "없음", cfg.effort or "기본")
    make_server(Bridge(cfg), host, port).serve_forever()


if __name__ == "__main__":
    main()
