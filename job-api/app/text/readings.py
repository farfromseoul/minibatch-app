"""영어 읽기 (2026-10-31 사용자: 영어가 너무 빠르고 어색하게 읽힌다).

Supertonic 은 한국어 모드로 읽어 문장 속 영어(pdf, docx, skill-creator 등)를 빠르고 어색하게 읽는다. 대본 LLM 이 대본에 나온
영어 단어마다 한글 읽기를 함께 내고(`readings`), TTS 는 공통 발음 사전(content/pronunciation.yaml)과 합쳐 읽는 말로 바꾼다.
자막은 영어 원문 그대로. 같은 단어가 둘 다에 있으면 운영자가 정한 공통 사전이 이긴다.
버린 대안: 영어 부분만 영어 목소리로 따로 합성(목소리·억양이 바뀜), 공통 사전만 손으로 늘리기(새 도구 이름이 늘 빠진다).
"""
from __future__ import annotations

import re
from typing import Any

from .pronunciation import apply_pronunciation

READING_TAG = "영어 읽기"
LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9.+#_/'-]*[A-Za-z0-9+#]|[A-Za-z]")
HANGUL_READING = re.compile(r"^[가-힣 ]+$")

SCHEMA = {"type": "array", "items": {"type": "object", "properties": {"term": {"type": "string"}, "reading": {"type": "string"}},
                                     "required": ["term", "reading"], "additionalProperties": False}}


def to_map(items: Any, sentences: list[str]) -> tuple[dict[str, str], list[str]]:
    """[{term, reading}] → {term: reading}. 읽기는 한글·띄어쓰기만, 단어는 대본에 실제로 나온 것만"""
    out: dict[str, str] = {}
    problems: list[str] = []
    text = "\n".join(sentences)
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        term, reading = str(it.get("term", "")).strip(), " ".join(str(it.get("reading", "")).split())
        if not term or not reading:
            continue
        if term not in text:
            problems.append(f"{READING_TAG}: '{term}' 은 대본에 없는 말이다. 대본에 나온 영어 단어만 readings 에 넣는다")
            continue
        if not HANGUL_READING.match(reading):
            problems.append(f"{READING_TAG}: '{term}' 의 읽기 '{reading}' 는 한글과 띄어쓰기로만 쓴다")
            continue
        out[term] = reading
    return out, problems


def merge(llm: dict[str, str], dictionary: dict[str, str]) -> dict[str, str]:
    """LLM 읽기 위에 공통 사전을 덮는다 (운영자가 정한 읽기가 이긴다)"""
    return {**llm, **dictionary}


def missing(sentences: list[str], words: dict[str, str]) -> list[str]:
    """읽기를 적용한 뒤에도 남는 영어 단어 (나온 순서, 중복 없이)"""
    left: list[str] = []
    for s in sentences:
        for w in LATIN_WORD.findall(apply_pronunciation(s, words)):
            if w not in left:
                left.append(w)
    return left


def fill(ctx, sentences: list[str], readings: dict[str, str], words: dict[str, str]) -> dict[str, str]:
    """대본이 통과된 뒤 읽기가 빠진 영어 단어만 모아 LLM 에 한 번 묻는다. 대본 전체를 다시 쓰지 않는다
    (읽기 하나로 대본을 다시 쓰면 Codex 호출이 늘고 잘 쓴 내용도 바뀐다). 실패하면 기록만 남기고 영어 그대로 읽는다"""
    from app.llm.prompting import render_messages
    from app.pipeline.steps.llm_common import ask

    left = missing(sentences, merge(readings, words))
    if not left:
        return readings
    used = [s for s in sentences if any(w in s for w in left)]
    messages, _ = render_messages("readings", sentences="\n".join(f"- {s}" for s in used), terms="\n".join(f"- {w}" for w in left))
    schema = {"type": "object", "properties": {"readings": SCHEMA}, "required": ["readings"], "additionalProperties": False}

    def check(d: Any) -> list[str]:
        got, problems = to_map(d.get("readings") if isinstance(d, dict) else None, sentences)
        still = missing(sentences, merge({**readings, **got}, words))
        return problems + ([f"이 단어의 읽기가 없다: {', '.join(still)}"] if still else [])
    try:
        out = ask(ctx, messages, schema, "readings", check)
        got, _ = to_map(out.data.get("readings") if isinstance(out.data, dict) else None, sentences)
    except Exception as e:  # 읽기를 못 받아도 영상은 만든다
        ctx.note_degraded(f"{READING_TAG}: 빠진 단어 읽기를 받지 못함({type(e).__name__}): {', '.join(left[:8])}")
        return readings
    result = {**readings, **got}
    still = missing(sentences, merge(result, words))
    if still:
        ctx.note_degraded(f"{READING_TAG}: 한글 읽기 없이 영어 그대로 읽는 단어: {', '.join(still[:8])}")
    return result
