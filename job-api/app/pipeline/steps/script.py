"""script 단계: 대본 생성 (앱 설계 "LLM 사용", "길이 맞추기", D23·D24).

- 목표 글자 수 = 목표 초 × TTS 초당 글자 수 × 0.9 (장면 사이 여백 몫). 0주 차 Supertonic 5.6 → 약 302자
- 문제(글자 수 ±10% 밖, 문장 길이 초과, 시리즈 필드 누락)는 알려 주며 최대 2번 다시 요청
- 끝까지 글자 수만 어긋나면 degraded 로 통과(timeline 단계가 실제 음성 길이로 다시 판정). 그 밖은 deterministic
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

from app.core.category import load_category
from app.llm.prompting import render, render_messages
from app.text.cta import outro_for
from app.text.sentences import count_chars, repeated_sentences, script_sentences

from .base import StepContext, StepFailure
from .llm_common import ask, meta_of

LENGTH_TAG = "글자 수"
# 대본 글자 수 허용 오차. 영상 길이 허용(55~65초)이 ±8% 라 그보다 좁게 둔다
# (2026-10-16 첫 전체 실행: ±10% 로 통과시킨 대본이 timeline 에서 66.3초로 걸림)
TOLERANCE = 0.07
TRIM_TO = 1.04
# 모델은 글자 수를 세는 데 약하고 문장 개수는 잘 지킨다. 2026-10-16 qwen/qwen3.8-27b 실측:
# 글자 수로 요청 → 302자 목표에 171자(8문장). 13문장으로 요청 → 13문장 230자(문장당 17.7자, "20자 이상" 지시는 안 지킴).
# 17문장으로 요청 → 351자(문장당 20.6자, 주제마다 다름). "줄여서·늘려서" 피드백은 잘 반영하지 못한다.
# 그래서 문장을 넉넉하게 요청하고, 길면 코드가 요약 바로 앞 설명 문장부터 빼서 맞춘다
# (끝부분 설명 문장은 앞 내용을 되풀이하는 경우가 많았다). 모델을 바꾸면 이 값을 다시 잰다
# 2026-10-17: 17자 기준이 문장을 뚝뚝 끊고 빈 비유 문장으로 채우게 해 24자로 늘렸다(대본 품질 개선)
CHARS_PER_SENTENCE = 24


def sentence_plan(target: int, max_sentence: int) -> tuple[int, int]:
    """(전체 문장 수, 문장당 권장 최소 글자)"""
    n = max(5, math.ceil(target / CHARS_PER_SENTENCE))
    return n, min(max_sentence - 20, 15)


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


COPY_RUN = 15  # 원문과 공백·문장부호 빼고 이만큼 연달아 같으면 옮긴 것으로 본다


def _bare(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text)


def copied_from(sentence: str, bare_source: str) -> bool:
    b = _bare(sentence)
    return any(b[i:i + COPY_RUN] in bare_source for i in range(0, max(0, len(b) - COPY_RUN) + 1)) if len(b) >= COPY_RUN else False


def _news_block(news: dict | None) -> str:
    if not news:
        return ""
    facts = "\n".join(f"- {f}" for f in news["facts"])
    return (f"IT 뉴스 해설이다. 출처: {news['sourceTitle']}. 왜 중요한가: {news['angle']}\n"
            f"아래 사실 목록 밖의 숫자·이름·날짜·주장은 쓰지 않는다. 사실 목록 문장을 그대로 옮기지 말고 진행자가 말하듯 새로 쓴다:\n{facts}\n")


OPTIONAL_SENTENCES = ("recap", "nextTeaser")  # 빼도 영상이 되는 문장 (1화·마지막 화에는 원래 없다)


def _drop_bad_optional(data: dict, max_sentence: int) -> tuple[dict, list[str]]:
    """지난 화 짚기·다음 화 예고 중 너무 길거나 다른 문장을 되풀이하는 것을 뺀다"""
    data, dropped = dict(data), []
    for key in OPTIONAL_SENTENCES:
        sentence = data.get(key)
        if not sentence:
            continue
        spoken = script_sentences(data)
        idx = spoken.index(sentence)
        repeated = any(idx in pair for pair in repeated_sentences(spoken))
        if count_chars(sentence) > max_sentence or repeated:
            dropped.append(data.pop(key))
    return data, dropped


def _review_feedback(ctx: StepContext) -> str:
    """다시 쓰는 대본이면 직전 검토에서 떨어진 이유 (마지막 개요 고침 뒤, 최근 2번).
    2026-10-21 실제: 되돌려서 같은 개요로 처음부터 다시 쓰니 '키 합의를 풀어 써라' 를 세 번 연속 받았다"""
    from app.db.models import Job
    from app.domain import stuck  # 단계 모듈이 도메인 전체를 먼저 불러오지 않게
    with ctx.db() as s:
        job = s.get(Job, ctx.job_id)
        errors = stuck.low_score_failures(s, job)[-2:] if job is not None else []
    if not errors:
        return ""
    lines = "\n".join(f"- {e[:700]}" for e in errors)
    return ("지난 대본이 검토에서 떨어졌다. 아래 지적을 이번 대본에서 반드시 고친다. 지적받은 표현은 그대로 쓰지 말고, "
            f"낯선 용어는 처음 나올 때 일상어로 풀어 쓴다:\n{lines}\n")


def _series_block(series: dict | None) -> str:
    if not series:
        return ""
    previous = "\n".join(f"- {p['episode']}화 {p['title']}: {p['summary'] or '(요약 없음)'}" for p in series["previous"]) or "- (첫 화)"
    text, _ = render(
        "series_block", series_title=series["title"], episode=series["episode"], total=series["totalEpisodes"],
        bible=json.dumps(series["bible"], ensure_ascii=False), previous=previous, outline=series["outline"],
        next_outline=series["nextOutline"] or "(마지막 화)",
        recap_rule=("recap: 앞 화 핵심을 짚어 이번 화 질문과 잇는 한 문장(25자 안팎). 예: '지난 화에서 단어가 숫자로 바뀌는 걸 봤는데, 그 숫자로 무엇을 할까요?' "
                    "(hook 바로 다음에 읽는다. body 에는 앞 화 이야기를 다시 쓰지 않는다)"
                    if series["episode"] > 1 else ""),
        teaser_rule=("nextTeaser: 다음 화에서 설명할 것을 궁금하게 만드는 질문 한 문장(25자 안팎). "
                     "'다음 화에서는 ~합니다' 같은 설명문은 쓰지 않는다. 예: '그럼 그 숫자로 어떻게 다음 단어를 고를까요?' (대본 맨 끝에 읽는다)"
                     if series["nextOutline"] else ""),
        closing_rule=("이번이 시리즈의 마지막 화다. summary 는 이번 화의 결론에 이어 시리즈 전체에서 배운 흐름을 한 문장으로 묶어 "
                      "시리즈를 마무리한다 (예: '토큰에서 샘플링까지, 이제 AI가 답을 만드는 과정이 보이죠.'). "
                      "끝 인사는 코드가 붙이므로 쓰지 않는다 (D26·D33)" if not series["nextOutline"] else ""))
    return text


class ScriptStep:
    name = "script"
    inputs = ["job.json"]
    outputs = ["script.json"]

    def run(self, ctx: StepContext) -> None:
        job = ctx.read_json("job.json")
        cat = load_category(ctx.settings, job["category"])
        if job.get("format") == "listicle":  # 목록형 쇼츠 (D42)
            from .listicle import run_script
            run_script(ctx, job, cat, _review_feedback(ctx))
            return
        rules = cat.get("script", {})
        max_sentence = int(rules.get("max_sentence_chars", 40))
        series = job.get("series")
        cps = ctx.providers.chars_per_sec
        target = round(job["targetDurationSec"] * cps * 0.9)
        outro = outro_for(cat, series)
        if outro:  # 끝 장면 문장(코드가 붙임)과 장면 여백(약 0.5초)만큼 대본을 줄인다 (D26)
            target -= count_chars(outro["line"]) + round(0.5 * cps)
        total_n, min_chars = sentence_plan(target, max_sentence)
        body_n = total_n - 2  # hook 1 + body + summary 1
        messages, version = render_messages(
            "script", topic=job["topic"], audience=cat.get("audience", ""), structure=rules.get("structure", ""),
            target_chars=target, max_sentence=max_sentence, forbidden=", ".join(rules.get("forbidden", [])),
            sentences=total_n, body_sentences=body_n, min_chars=min_chars, series_block=_series_block(series),
            news_block=_news_block(job.get("news")), review_feedback=_review_feedback(ctx))
        source = _bare(ctx.path("news_source.txt").read_text(encoding="utf-8")) if job.get("news") and ctx.path("news_source.txt").exists() else ""
        schema = _schema(series, body_n)

        def check(data: Any, need_optional: bool = True) -> list[str]:
            problems = []
            required = [k for k in schema["required"] if need_optional or k not in OPTIONAL_SENTENCES]
            missing = [k for k in required if not data.get(k)] if isinstance(data, dict) else required
            if missing:
                return [f"{k} 가 없다" + (" (recap: 앞 화 핵심을 짚는 한 문장)" if k == "recap" else "") for k in missing]
            spoken = script_sentences(data)
            for i, j in repeated_sentences(spoken):  # 2026-10-18: recap 이 body 에 또 나옴, summary 가 body 를 되풀이
                problems.append(f"{j + 1}번째 문장이 {i + 1}번째 문장을 되풀이한다. 새 내용으로 바꾼다: {spoken[j]}")
            for i, sentence in enumerate(spoken, start=1):
                if source and copied_from(sentence, source):  # IT 뉴스: 원문·GeekNews 요약 표현 그대로 금지 (D40)
                    problems.append(f"{i}번째 문장이 원문 표현을 그대로 옮겼다. 사실은 두고 우리 말로 바꿔 쓴다: {sentence}")
                if count_chars(sentence) > max_sentence:
                    problems.append(f"{i}번째 문장이 {count_chars(sentence)}자다. {max_sentence}자 이내로 나눈다: {sentence}")
            # 말하는 문장 전부(지난 이야기·다음 화 예고 포함)를 센다
            # (2026-10-16 시리즈 2화: 후킹~요약만 세서 253자로 통과했지만 실제 318자, 영상 72.7초)
            total = sum(count_chars(t) for t in script_sentences(data))
            if abs(total - target) > target * TOLERANCE:
                gap = abs(target - total)
                more = math.ceil(gap / CHARS_PER_SENTENCE)
                if total < target:
                    problems.append(f"{LENGTH_TAG}가 {total}자로 목표 {target}자보다 {gap}자 짧다. body 에 작동 원리 단계나 실제 예시 문장을 약 {more}개 더 넣어 늘려서 쓴다 (문장마다 {min_chars}자 이상)")
                else:
                    problems.append(f"{LENGTH_TAG}가 {total}자로 목표 {target}자보다 {gap}자 길다. body 문장을 약 {more}개 빼서 줄여서 쓴다")
            return problems

        def trim(data: Any) -> Any:
            """길면 body 끝 문장부터 빼서 목표 +4% 안으로 (body 는 최소 3문장 남긴다)"""
            if not isinstance(data, dict) or not isinstance(data.get("body"), list):
                return data
            data = dict(data, body=list(data["body"]))
            ctx.meta["trimmed"] = []  # 시도마다 새로 센다

            def total() -> int:
                return sum(count_chars(t) for t in script_sentences(data)) if data.get("hook") and data.get("summary") else 0
            # 빼고 나서도 하한(목표 −7%) 이상일 때만 뺀다. 너무 빼서 짧아지지 않게
            while (total() > target * TRIM_TO and len(data["body"]) > 3
                   and total() - count_chars(data["body"][-1]) >= target * (1 - TOLERANCE)):
                ctx.meta.setdefault("trimmed", []).append(data["body"].pop())
            return data

        out = ask(ctx, messages, schema, "script", check, adjust=trim)
        data, dropped = out.data, []
        hard = [p for p in out.problems if not p.startswith(LENGTH_TAG)]
        if hard and isinstance(data, dict) and data.get("hook"):
            # 다시 물어도 지난 화 짚기·다음 화 예고만 규칙을 어기면 그 문장을 빼고 쓴다 (2026-10-24 실제: 4화 recap 이
            # 되풀이·49자로 세 번 떨어져 시리즈가 멈췄다). 후킹·본문·요약 문제는 그대로 실패
            data, dropped = _drop_bad_optional(data, max_sentence)
            if dropped:
                hard = [p for p in check(data, need_optional=False) if not p.startswith(LENGTH_TAG)]
                ctx.note_degraded("규칙을 어긴 문장을 뺐다: " + " / ".join(dropped))
        if hard:
            raise StepFailure("deterministic", "대본 규칙을 지키지 못했다: " + "; ".join(hard)[:800], retry_from="script")
        if out.problems:  # 글자 수만 어긋남
            ctx.note_degraded("; ".join(out.problems))
        data = dict(data)
        chars = sum(count_chars(t) for t in script_sentences(data))
        data["meta"] = meta_of(out, version, targetChars=target, charCount=chars, trimmedSentences=ctx.meta.get("trimmed", []),
                               droppedSentences=dropped)
        ctx.write_json("script.json", data)
