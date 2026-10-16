"""LLM 어댑터 계약 (앱 설계 "LLM 어댑터"). 단계 코드는 이 모양만 안다.

지금 구현은 openai-compatible(LM Studio) 하나다. claude-api 는 나중에 같은 계약으로 더한다(D16).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class LlmError(Exception):
    """kind: transient(서버 응답 없음·시간 초과·5xx, 다시 하면 될 수 있음) | invalid_output(JSON 이 아님)"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass
class LlmResult:
    data: Any  # 꺼낸 JSON (스키마 검증 전)
    model: str  # 실제 응답한 모델 이름
    input_tokens: int | None
    output_tokens: int | None
    source: str  # content | reasoning_content (생각 모델이 답을 어디에 넣었나)
    raw: str  # 응답 원문 (디버깅용)


class LlmEngine(Protocol):
    name: str

    def generate_json(self, messages: list[dict], schema: dict, schema_name: str) -> LlmResult: ...
