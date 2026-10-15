"""대본 JSON 검증과 글자 수 계산. 규칙은 앱 설계(04)의 "LLM 사용" 절을 따른다."""
from __future__ import annotations

from typing import Any, List

SPOKEN_KEYS = ("hook", "body", "summary")


def _sentences(script: dict) -> List[tuple]:
    """(위치 이름, 문장) 목록. 소리 내어 읽는 부분만."""
    items = []
    if isinstance(script.get("hook"), str):
        items.append(("hook", script["hook"]))
    body = script.get("body")
    if isinstance(body, list):
        items.extend((f"body[{i}]", s) for i, s in enumerate(body) if isinstance(s, str))
    if isinstance(script.get("summary"), str):
        items.append(("summary", script["summary"]))
    return items


def validate_script(script: Any, max_sentence_chars: int = 40) -> List[str]:
    """문제 목록을 돌려준다. 비어 있으면 통과."""
    if not isinstance(script, dict):
        return ["대본이 JSON 객체가 아니다"]
    problems = []
    for key in ("hook", "body", "summary", "titleCandidates"):
        if key not in script:
            problems.append(f"{key} 없음")
    for key in ("hook", "summary"):
        if key in script and not isinstance(script[key], str):
            problems.append(f"{key} 가 문자열이 아니다")
    body = script.get("body")
    if "body" in script and not (isinstance(body, list) and all(isinstance(s, str) for s in body)):
        problems.append("body 가 문자열 목록이 아니다")
    titles = script.get("titleCandidates")
    if "titleCandidates" in script and not (isinstance(titles, list) and len(titles) == 3):
        problems.append("titleCandidates 는 3개여야 한다")
    for where, sentence in _sentences(script):
        if len(sentence) > max_sentence_chars:
            problems.append(f"{where} 가 {max_sentence_chars}자를 넘는다 ({len(sentence)}자)")
    return problems


def count_chars(value: Any) -> int:
    """공백을 뺀 글자 수. 대본(dict)이면 읽는 부분(hook, body, summary)만 센다."""
    if isinstance(value, dict):
        return sum(count_chars(s) for _, s in _sentences(value))
    if isinstance(value, str):
        return sum(1 for ch in value if not ch.isspace())
    return 0
