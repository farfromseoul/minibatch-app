"""OpenAI 호환 /v1/chat/completions 호출 (표준 라이브러리만 쓴다).

LM Studio 문서의 구조화 출력 형식: response_format = {type: json_schema, json_schema: {name, strict, schema}}.
"""
from __future__ import annotations

import json
import time
import urllib.request
from typing import Any, Dict, List, Optional


def chat(
    base_url: str,
    model: str,
    messages: List[Dict[str, str]],
    schema: Optional[dict] = None,
    extra: Optional[dict] = None,
    temperature: float = 0.2,
    timeout_sec: float = 600,
) -> Dict[str, Any]:
    """요청 하나를 보내고 {message, completion_tokens, elapsed_sec, raw} 를 돌려준다."""
    body: Dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature, "stream": False}
    if schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "answer", "strict": True, "schema": schema},
        }
    if extra:
        body.update(extra)
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        raw = json.loads(response.read())
    elapsed = time.monotonic() - started
    return {
        "message": raw["choices"][0]["message"],
        "completion_tokens": (raw.get("usage") or {}).get("completion_tokens"),
        "elapsed_sec": elapsed,
        "raw": raw,
    }
