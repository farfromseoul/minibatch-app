"""OpenAI 호환 응답의 message 에서 JSON 답을 꺼낸다.

생각(thinking) 모델은 답을 content 가 아니라 reasoning_content 에 넣기도 한다
(2026-10-15 LM Studio + qwen/qwen3.8-27b 에서 확인). content 를 먼저 보고,
없으면 reasoning_content 를 본다. 이 규칙은 job-api 의 LLM 어댑터로 옮겨 간다.
"""
from __future__ import annotations

import json
import re
from typing import Any, Tuple

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class ExtractError(ValueError):
    """어느 필드에서도 JSON 답을 찾지 못했다."""


def _parse(text: Any) -> Any:
    if not isinstance(text, str):
        raise ValueError("텍스트 아님")
    cleaned = _THINK_BLOCK.sub("", text).strip()
    if not cleaned:
        raise ValueError("비어 있음")
    return json.loads(cleaned)


def extract_json(message: dict) -> Tuple[Any, str]:
    """(답, 꺼낸 필드 이름)을 돌려준다. 못 찾으면 ExtractError."""
    for field in ("content", "reasoning_content"):
        try:
            return _parse(message.get(field)), field
        except ValueError:
            continue
    raise ExtractError("content 와 reasoning_content 어디에도 JSON 이 없다")
