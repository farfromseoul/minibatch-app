"""프롬프트 파일 (앱 설계: 프롬프트는 llm/prompts/*.md, 버전을 산출물에 기록).

$이름 자리에 값을 넣는다(string.Template). JSON 예시의 중괄호와 섞이지 않는다.
<이름>.system.md 가 있으면 system 메시지(역할·구조·금지 규칙), <이름>.md 는 user 메시지(이번 주제·분량)로 보낸다
(2026-10-17: 규칙과 이번 요청을 나누면 모델이 규칙을 더 잘 지키는 편이다).
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


def render_messages(name: str, **values: object) -> tuple[list[dict], str]:
    """([system?, user] 메시지, 버전=두 파일 내용 해시 앞 12자리)"""
    user = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    sys_path = PROMPTS / f"{name}.system.md"
    system = sys_path.read_text(encoding="utf-8") if sys_path.exists() else ""
    vals = {k: str(v) for k, v in values.items()}
    version = hashlib.sha256((system + "\n----\n" + user).encode()).hexdigest()[:12]
    msgs = [{"role": "system", "content": Template(system).substitute(vals)}] if system else []
    msgs.append({"role": "user", "content": Template(user).substitute(vals)})
    return msgs, version
