"""OpenAI 호환 /v1/chat/completions (LM Studio, Ollama 등). 0주 차 poc/llm_compare 의 규칙을 옮겼다.

- 구조화 출력: response_format = {type: json_schema, json_schema: {name, strict, schema}} (LM Studio 공식 문서)
- 생각(thinking) 모델은 답을 reasoning_content 에 넣기도 한다(2026-10-15 qwen/qwen3.8-27b 확인). content 가 비면 그쪽을 본다
- <think>…</think> 와 ```json 코드 울타리를 벗긴다
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .base import LlmError, LlmResult

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _parse(text: Any) -> Any:
    if not isinstance(text, str):
        raise ValueError("텍스트 아님")
    cleaned = _THINK.sub("", text).strip()
    m = _FENCE.match(cleaned)
    if m:
        cleaned = m.group(1).strip()
    if not cleaned:
        raise ValueError("비어 있음")
    return json.loads(cleaned)


class OpenAiCompatible:
    name = "openai-compatible"

    def __init__(self, *, base_url: str, model: str, structured_output: str = "json_schema",
                 extra_body: dict | None = None, timeout_sec: float = 300, temperature: float = 0.3,
                 prompt_suffix: str = ""):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.structured_output = structured_output
        self.extra_body = extra_body or {}
        self.timeout_sec = timeout_sec
        self.temperature = temperature
        self.prompt_suffix = prompt_suffix  # 생각 끄기 지시 등 모델별 문구 (설정으로만)

    def generate_json(self, messages: list[dict], schema: dict, schema_name: str) -> LlmResult:
        msgs = [dict(m) for m in messages]
        if self.prompt_suffix and msgs and msgs[-1]["role"] == "user":
            msgs[-1]["content"] += "\n" + self.prompt_suffix
        body: dict[str, Any] = {"model": self.model, "messages": msgs, "temperature": self.temperature, "stream": False}
        if self.structured_output == "json_schema":
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": schema_name, "strict": True, "schema": schema}}
        elif self.structured_output == "json_object":
            body["response_format"] = {"type": "json_object"}
        body.update(self.extra_body)  # 서버 전용 옵션(LM Studio 의 ttl 등)
        try:
            res = httpx.post(f"{self.base_url}/chat/completions", json=body, timeout=self.timeout_sec)
        except httpx.TimeoutException as e:
            raise LlmError("transient", f"LLM 서버 시간 초과({self.timeout_sec}초)") from e
        except httpx.HTTPError as e:
            raise LlmError("transient", f"LLM 서버 연결 실패: {type(e).__name__}") from e
        if res.status_code >= 500 or res.status_code in (408, 429):
            raise LlmError("transient", f"LLM 서버 오류 {res.status_code}")
        if res.status_code >= 400:
            raise LlmError("invalid_output", f"LLM 요청 거절 {res.status_code}: {res.text[:300]}")
        raw = res.json()
        message = raw["choices"][0]["message"]
        usage = raw.get("usage") or {}
        for field in ("content", "reasoning_content"):
            try:
                data = _parse(message.get(field))
            except ValueError:
                continue
            return LlmResult(data=data, model=raw.get("model", self.model), input_tokens=usage.get("prompt_tokens"),
                             output_tokens=usage.get("completion_tokens"), source=field, raw=json.dumps(raw, ensure_ascii=False))
        raise LlmError("invalid_output", f"content 와 reasoning_content 어디에도 JSON 이 없다: {str(message.get('content'))[:200]}")
