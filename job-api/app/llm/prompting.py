"""프롬프트 파일 (앱 설계: 프롬프트는 llm/prompts/*.md, 버전을 산출물에 기록).

$이름 자리에 값을 넣는다(string.Template). JSON 예시의 중괄호와 섞이지 않는다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from string import Template

PROMPTS = Path(__file__).parent / "prompts"


def render(name: str, **values: object) -> tuple[str, str]:
    """(채운 프롬프트, 버전=파일 내용 해시 앞 12자리)"""
    text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    version = hashlib.sha256(text.encode()).hexdigest()[:12]
    return Template(text).substitute({k: str(v) for k, v in values.items()}), version
