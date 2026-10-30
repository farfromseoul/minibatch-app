"""review 단계: 규칙 검사(LLM 없이) + LLM 자기 검토 (앱 설계 "LLM 사용", "규칙 검사").

치명 오류(문장 길이 초과, LLM 이 critical 로 지적한 사실 오류)는 deterministic 실패, retry_from=script.
2026-10-17: 정확성·이해 쉬움·구체성·자연스러움을 1~5점으로 매기고, 2점 이하가 하나라도 있으면 대본부터 다시.
"""
from __future__ import annotations

import re
from typing import Any

from app.core.category import load_category
from app.llm.prompting import render_messages
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
        "scores": {"type": "object", "properties": {k: {"type": "integer", "minimum": 1, "maximum": 5} for k in
                                                    ("accuracy", "clarity", "concreteness", "naturalness")},
                   "required": ["accuracy", "clarity", "concreteness", "naturalness"], "additionalProperties": False},
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
    },
    "required": ["issues", "scores", "verdict"],
    "additionalProperties": False,
}

NUMBER = re.compile(r"\d")
SCORE_NAMES = {"accuracy": "정확성", "clarity": "이해 쉬움", "concreteness": "구체성", "naturalness": "자연스러움"}
MIN_SCORE = 3  # 이 점수 밑(2점 이하)이 하나라도 있으면 대본부터 다시


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
        news = job.get("news")
        series_facts = (((job.get("series") or {}).get("bible") or {}).get("facts")
                        or (job.get("listicle") or {}).get("facts") or [])  # 사용자가 준 참고 자료 (2026-10-30, 목록형 D42)
        if news:
            facts = ("\n원문 사실 목록(IT 뉴스, D40). 대본의 숫자·이름·날짜·주장이 이 목록과 다르거나 목록에 없으면 critical:\n"
                     + "\n".join(f"- {f}" for f in news["facts"]) + "\n")
        elif series_facts:
            facts = ("\n참고 자료에서 확인한 사실. 대본의 도구 이름·기능·숫자가 이와 다르면 critical:\n"
                     + "\n".join(f"- {f}" for f in series_facts) + "\n")
        else:
            facts = ""
        messages, version = render_messages("review", topic=job["topic"], audience=cat.get("audience", ""), numbered=numbered,
                                            rules=", ".join(cat.get("review", {}).get("rules", ["사실 오류"])), facts=facts)

        def check(d: Any) -> list[str]:
            if not (isinstance(d, dict) and isinstance(d.get("issues"), list) and d.get("verdict") in ("pass", "fail")):
                return ["issues 배열과 verdict(pass|fail) 가 필요하다"]
            sc = d.get("scores")
            if not isinstance(sc, dict) or any(not isinstance(sc.get(k), int) for k in SCORE_NAMES):
                return ["scores 에 accuracy·clarity·concreteness·naturalness 를 1~5 정수로 넣는다"]
            return []

        out = ask(ctx, messages, SCHEMA, "review", check)
        if out.problems:
            raise StepFailure("deterministic", "검토 응답 형식이 맞지 않다", retry_from="review")
        critical = [x for x in out.data["issues"] if x.get("severity") == "critical"]
        if critical:
            reasons = "; ".join(f"{x.get('line')}번: {x.get('reason')}" for x in critical)
            raise StepFailure("deterministic", f"검토에서 치명 오류: {reasons}"[:800], retry_from="script")
        scores = out.data["scores"]
        low = [k for k in SCORE_NAMES if scores[k] < MIN_SCORE]
        if low:
            why = "; ".join(f"{x.get('line')}번: {x.get('reason')}" for x in out.data["issues"])
            raise StepFailure("deterministic", (f"검토 점수 미달: {', '.join(f'{SCORE_NAMES[k]} {scores[k]}점' for k in low)}"
                                                f" ({why})")[:800], retry_from="script")
        ctx.write_json("review.json", {"verdict": "pass", "issues": out.data["issues"], "scores": scores,
                                       "ruleWarnings": warnings, "meta": meta_of(out, version)})
