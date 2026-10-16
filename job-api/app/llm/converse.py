"""LLM 에 묻고, 검사하고, 문제를 알려 주며 다시 묻는다 (앱 설계: 스키마·규칙 실패 시 재요청).

일시적 실패(서버 응답 없음)는 여기서 다시 묻지 않고 LlmError(transient) 그대로 올린다. 재시도는 n8n 이 정한다(D20).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .base import LlmEngine, LlmError, LlmResult


@dataclass
class Outcome:
    data: Any
    result: Optional[LlmResult]
    attempts: int
    problems: list[str] = field(default_factory=list)  # 마지막 응답에 남은 문제 (비면 통과)
    input_tokens: int = 0
    output_tokens: int = 0


def converse(llm: LlmEngine, messages: list[dict], schema: dict, schema_name: str,
             check: Callable[[Any], list[str]], max_attempts: int = 3,
             adjust: Optional[Callable[[Any], Any]] = None) -> Outcome:
    """adjust: 검사 전에 코드가 확실히 고칠 수 있는 것을 고친다(예: 긴 대본 끝 문장 빼기)"""
    history = list(messages)
    out = Outcome(data=None, result=None, attempts=0)
    for attempt in range(1, max_attempts + 1):
        out.attempts = attempt
        try:
            r = llm.generate_json(history, schema, schema_name)
        except LlmError as e:
            if e.kind == "transient":
                raise
            out.problems = [f"JSON 형식으로만 답하라 ({e.message[:100]})"]
            answer_text = ""
        else:
            out.result, out.data = r, (adjust(r.data) if adjust else r.data)
            out.input_tokens += r.input_tokens or 0
            out.output_tokens += r.output_tokens or 0
            out.problems = check(out.data)
            answer_text = json.dumps(r.data, ensure_ascii=False)
        if not out.problems:
            return out
        if attempt < max_attempts:
            history = history + [
                {"role": "assistant", "content": answer_text},
                {"role": "user", "content": "다음 문제를 고쳐서 같은 JSON 형식으로 다시 답하라:\n"
                                            + "\n".join(f"- {p}" for p in out.problems)},
            ]
    return out
