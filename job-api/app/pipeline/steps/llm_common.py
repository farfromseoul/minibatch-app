"""LLM 단계 공통: 제공자 고르기, 일시적 실패 변환, 기록 모양."""
from __future__ import annotations

from typing import Any, Callable

from app.llm.base import LlmError
from app.llm.converse import Outcome, converse

from .base import StepContext, StepFailure


def ask(ctx: StepContext, messages: list[dict], schema: dict, schema_name: str,
        check: Callable[[Any], list[str]], adjust: Callable[[Any], Any] | None = None) -> Outcome:
    if ctx.providers is None:
        raise StepFailure("deterministic", "LLM 제공자 설정(providers.yaml)이 없다")
    llm = ctx.providers.llm(ctx.step)
    try:
        return converse(llm, messages, schema, schema_name, check, adjust=adjust)
    except LlmError as e:  # transient 만 여기까지 올라온다
        raise StepFailure("transient", e.message) from e


def meta_of(out: Outcome, version: str, **extra: Any) -> dict[str, Any]:
    r = out.result
    return {"model": r.model if r else None, "promptVersion": version, "attempts": out.attempts,
            "source": r.source if r else None, "inputTokens": out.input_tokens, "outputTokens": out.output_tokens,
            **extra}
