"""주제 정규화 키 (기획서 F2 중복 검사). "RAG란?", "rag 란" → "rag"."""
from __future__ import annotations

import re
import unicodedata

# "~란?", "~이란 무엇인가" 처럼 주제 뒤에 붙는 말. 긴 것부터 하나만 뗀다.
# 한 글자 조사(은·는·이·가)는 떼지 않는다: 단어 끝 글자와 구분할 수 없다.
_SUFFIXES = ["이란무엇인가", "란무엇인가", "이란뭘까", "란뭘까", "이란", "란"]


def normalize_topic(title: str) -> str:
    s = unicodedata.normalize("NFKC", title).lower()
    s = re.sub(r"[\s\W_]+", "", s)  # 공백·문장 부호 제거 (한글·영문·숫자만 남는다)
    for suffix in _SUFFIXES:
        if s.endswith(suffix) and len(s) > len(suffix):
            return s[: -len(suffix)]
    return s
