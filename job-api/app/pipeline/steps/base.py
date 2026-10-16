"""단계 계약 (앱 설계 "단계 계약", "재시도와 실패 종류").

단계는 앞 단계의 파일만 읽고 자기 파일만 쓴다. 실패는 StepFailure 로 종류를 알려 준다.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

FAILURE_KINDS = ("transient", "deterministic", "quota")


class StepFailure(Exception):
    def __init__(self, kind: str, message: str, retry_from: Optional[str] = None,
                 retry_at: Optional[str] = None):
        if kind not in FAILURE_KINDS:
            raise ValueError(f"모르는 실패 종류: {kind}")
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.retry_from = retry_from
        self.retry_at = retry_at


@dataclass
class StepContext:
    job_id: str
    step: str
    attempt: int
    job_dir: Path
    job: dict[str, Any]  # DB 의 작업 정보 (topic, category, series 등)
    settings: Any
    db: Callable  # 세션을 여는 함수 (topic 단계처럼 DB 가 필요한 단계만 쓴다)
    providers: Any = None  # ProviderRegistry (LLM·TTS 단계가 쓴다)
    written: list[Path] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)  # 토큰 등 시도 기록
    degraded_notes: list[str] = field(default_factory=list)

    def path(self, rel: str) -> Path:
        return self.job_dir / rel

    def write_text(self, rel: str, text: str) -> Path:
        """임시 이름으로 쓰고 끝나면 이름을 바꾼다 (규칙 5: 원자적 쓰기)."""
        target = self.path(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f"{target.name}.tmp-{self.attempt}")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)
        self.written.append(target)
        return target

    def write_json(self, rel: str, data: Any) -> Path:
        return self.write_text(rel, json.dumps(data, ensure_ascii=False, indent=2))

    def read_json(self, rel: str) -> Any:
        return json.loads(self.path(rel).read_text(encoding="utf-8"))

    def note_degraded(self, message: str) -> None:
        """일부만 실패했지만 계속 갈 수 있을 때 (degraded). 실패로 치지 않고 기록만 남긴다."""
        self.degraded_notes.append(message)


class Step(Protocol):
    name: str
    inputs: list[str]  # 작업 폴더 기준 입력 파일·폴더
    outputs: list[str]  # 작업 폴더 기준 출력 파일·폴더

    def run(self, ctx: StepContext) -> None: ...
