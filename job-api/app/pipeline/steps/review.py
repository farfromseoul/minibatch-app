"""review 단계: 규칙 검사(LLM 없이) + LLM 자기 검토 (앱 설계 "LLM 사용", "규칙 검사").

치명 오류(문장 길이 초과, LLM 이 critical 로 지적한 사실 오류)는 deterministic 실패, retry_from=script.
"""
from __future__ import annotations

import re
from typing import Any

from app.core.category import load_category
from app.llm.prompting import render
from app.text.sentences import count_chars, script_sentences

from .base import StepContext, StepFailure
from .llm_common import ask, meta_of

SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {"type": "array", "items": {
            "type": "object",
            "properties": {"line": {"type": "integer"}, "severity": {"type": "string", "enum": ["critical", "warning", "info"]},
                           "reason": {"type": "string"}},
            "required": ["line", "severity", "reason"], "additionalProperties": False}},
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
    },
    "required": ["issues", "verdict"],
    "additionalProperties": False,
}

NUMBER = re.compile(r"\d")


class ReviewStep:
    name = "review"
    inputs = ["script.json"]
    outputs = ["review.json"]

    def run(self, ctx: StepContext) -> None:
        script = ctx.read_json("script.json")
        job = ctx.read_json("job.json")
        cat = load_category(ctx.settings, job["category"])
        max_sentence = int(cat.get("script", {}).get("max_sentence_chars", 40))
        banned = cat.get("review", {}).get("banned_words", [])
        sentences = script_sentences(script)

        warnings: list[dict[str, Any]] = []
        for i, s in enumerate(sentences, start=1):
            if count_chars(s) > max_sentence:
                raise StepFailure("deterministic", f"{i}번째 문장이 {count_chars(s)}자 (> {max_sentence}): {s}", retry_from="script")
            for w in banned:
                if w in s:
                    warnings.append({"rule": "banned_word", "line": i, "text": w})
            if NUMBER.search(s):  # 숫자·연도는 검토 화면에서 강조 (출처 확인)
                warnings.append({"rule": "number", "line": i, "text": s})

        numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(sentences, start=1))
        prompt, version = render("review", topic=job["topic"], audience=cat.get("audience", ""), numbered=numbered,
                                 rules=", ".join(cat.get("review", {}).get("rules", ["사실 오류"])))
        out = ask(ctx, [{"role": "user", "content": prompt}], SCHEMA, "review",
                  lambda d: [] if isinstance(d, dict) and isinstance(d.get("issues"), list) and d.get("verdict") in ("pass", "fail")
                  else ["issues 배열과 verdict(pass|fail) 가 필요하다"])
        if out.problems:
            raise StepFailure("deterministic", "검토 응답 형식이 맞지 않다", retry_from="review")
        critical = [x for x in out.data["issues"] if x.get("severity") == "critical"]
        if critical:
            reasons = "; ".join(f"{x.get('line')}번: {x.get('reason')}" for x in critical)
            raise StepFailure("deterministic", f"검토에서 치명 오류: {reasons}"[:800], retry_from="script")
        ctx.write_json("review.json", {"verdict": "pass", "issues": out.data["issues"], "ruleWarnings": warnings,
                                       "meta": meta_of(out, version)})
