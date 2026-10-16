"""script 단계: 대본 생성 (앱 설계 "LLM 사용", "길이 맞추기", D23·D24).

- 목표 글자 수 = 목표 초 × TTS 초당 글자 수 × 0.9 (장면 사이 여백 몫). 0주 차 Supertonic 5.6 → 약 302자
- 문제(글자 수 ±10% 밖, 문장 길이 초과, 시리즈 필드 누락)는 알려 주며 최대 2번 다시 요청
- 끝까지 글자 수만 어긋나면 degraded 로 통과(timeline 단계가 실제 음성 길이로 다시 판정). 그 밖은 deterministic
"""
from __future__ import annotations

import json
import math
from typing import Any

from app.core.category import load_category
from app.llm.prompting import render
from app.text.sentences import count_chars, script_sentences

from .base import StepContext, StepFailure
from .llm_common import ask, meta_of

LENGTH_TAG = "글자 수"
# 모델은 글자 수를 세는 데 약하고 문장 개수는 잘 지킨다. 2026-10-16 qwen/qwen3.8-27b 실측:
# 글자 수로 요청 → 302자 목표에 171자(8문장). 13문장으로 요청 → 13문장 230자(문장당 17.7자, "20자 이상" 지시는 안 지킴).
# 17문장으로 요청 → 351자(문장당 20.6자, 주제마다 다름). "줄여서·늘려서" 피드백은 잘 반영하지 못한다.
# 그래서 문장을 넉넉하게(문장당 17자 기준) 요청하고, 길면 코드가 요약 바로 앞 설명 문장부터 빼서 맞춘다
# (끝부분 설명 문장은 앞 내용을 되풀이하는 경우가 많았다). 모델을 바꾸면 이 값을 다시 잰다
CHARS_PER_SENTENCE = 17


def sentence_plan(target: int, max_sentence: int) -> tuple[int, int]:
    """(전체 문장 수, 문장당 권장 최소 글자)"""
    n = max(5, math.ceil(target / CHARS_PER_SENTENCE))
    return n, min(max_sentence - 10, 20)


def _schema(series: dict | None, body_n: int) -> dict:
    s = {"type": "string"}
    props: dict[str, Any] = {
        "hook": s,
        "body": {"type": "array", "items": s, "minItems": max(3, body_n - 1), "maxItems": body_n + 2},
        "summary": s,
        "titleCandidates": {"type": "array", "items": s, "minItems": 3, "maxItems": 3},
        "hashtags": {"type": "array", "items": s, "minItems": 1, "maxItems": 5},
    }
    if series:
        props["episodeSummary"] = s
        if series["episode"] > 1:
            props["recap"] = s
        if series["nextOutline"]:
            props["nextTeaser"] = s
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _series_block(series: dict | None) -> str:
    if not series:
        return ""
    previous = "\n".join(f"- {p['episode']}화 {p['title']}: {p['summary'] or '(요약 없음)'}" for p in series["previous"]) or "- (첫 화)"
    text, _ = render(
        "series_block", series_title=series["title"], episode=series["episode"], total=series["totalEpisodes"],
        bible=json.dumps(series["bible"], ensure_ascii=False), previous=previous, outline=series["outline"],
        next_outline=series["nextOutline"] or "(마지막 화)",
        recap_rule=("recap: '지난 이야기'로 시작하는 한 문장. 앞 화를 이어받는다 (대본 맨 앞에 읽는다)"
                    if series["episode"] > 1 else ""),
        teaser_rule=("nextTeaser: 다음 화를 궁금하게 만드는 한 문장 (대본 맨 끝에 읽는다)" if series["nextOutline"] else ""))
    return text


class ScriptStep:
    name = "script"
    inputs = ["job.json"]
    outputs = ["script.json"]

    def run(self, ctx: StepContext) -> None:
        job = ctx.read_json("job.json")
        cat = load_category(ctx.settings, job["category"])
        rules = cat.get("script", {})
        max_sentence = int(rules.get("max_sentence_chars", 40))
        target = round(job["targetDurationSec"] * ctx.providers.chars_per_sec * 0.9)
        series = job.get("series")
        total_n, min_chars = sentence_plan(target, max_sentence)
        body_n = total_n - 2  # hook 1 + body + summary 1
        prompt, version = render(
            "script", topic=job["topic"], audience=cat.get("audience", ""), structure=rules.get("structure", ""),
            target_chars=target, max_sentence=max_sentence, forbidden=", ".join(rules.get("forbidden", [])),
            sentences=total_n, body_sentences=body_n, min_chars=min_chars, series_block=_series_block(series))
        schema = _schema(series, body_n)

        def check(data: Any) -> list[str]:
            problems = []
            missing = [k for k in schema["required"] if not data.get(k)] if isinstance(data, dict) else schema["required"]
            if missing:
                return [f"{k} 가 없다" + (" (recap: '지난 이야기'로 시작하는 한 문장)" if k == "recap" else "") for k in missing]
            for i, sentence in enumerate(script_sentences(data), start=1):
                if count_chars(sentence) > max_sentence:
                    problems.append(f"{i}번째 문장이 {count_chars(sentence)}자다. {max_sentence}자 이내로 나눈다: {sentence}")
            total = sum(count_chars(t) for t in [data["hook"], *data["body"], data["summary"]])
            if abs(total - target) > target * 0.1:
                gap = abs(target - total)
                more = math.ceil(gap / CHARS_PER_SENTENCE)
                if total < target:
                    problems.append(f"{LENGTH_TAG}가 {total}자로 목표 {target}자보다 {gap}자 짧다. body 에 예시·비유 문장을 약 {more}개 더 넣어 늘려서 쓴다 (문장마다 {min_chars}자 이상)")
                else:
                    problems.append(f"{LENGTH_TAG}가 {total}자로 목표 {target}자보다 {gap}자 길다. body 문장을 약 {more}개 빼서 줄여서 쓴다")
            return problems

        def trim(data: Any) -> Any:
            """길면 body 끝 문장부터 빼서 목표 +5% 안으로 (body 는 최소 3문장 남긴다)"""
            if not isinstance(data, dict) or not isinstance(data.get("body"), list):
                return data
            data = dict(data, body=list(data["body"]))
            ctx.meta["trimmed"] = []  # 시도마다 새로 센다

            def total() -> int:
                return sum(count_chars(t) for t in [data.get("hook", ""), *data["body"], data.get("summary", "")])
            while total() > target * 1.05 and len(data["body"]) > 3:
                ctx.meta.setdefault("trimmed", []).append(data["body"].pop())
            return data

        out = ask(ctx, [{"role": "user", "content": prompt}], schema, "script", check, adjust=trim)
        hard = [p for p in out.problems if not p.startswith(LENGTH_TAG)]
        if hard:
            raise StepFailure("deterministic", "대본 규칙을 지키지 못했다: " + "; ".join(hard)[:800], retry_from="script")
        if out.problems:  # 글자 수만 어긋남
            ctx.note_degraded("; ".join(out.problems))
        data = dict(out.data)
        chars = sum(count_chars(t) for t in [data["hook"], *data["body"], data["summary"]])
        data["meta"] = meta_of(out, version, targetChars=target, charCount=chars, trimmedSentences=ctx.meta.get("trimmed", []))
        ctx.write_json("script.json", data)
