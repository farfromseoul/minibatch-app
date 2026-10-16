"""내부 토큰 인증. n8n 이 Authorization: Bearer <토큰> 으로 부른다 (아키텍처 "보안").

토큰 값은 파일(compose secret)에서 시작할 때 한 번 읽는다. 로그에 남기지 않는다.
"""
from __future__ import annotations

import hmac
from pathlib import Path

from fastapi import Request

from .errors import ApiError


def load_token(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"job-api 토큰 파일이 없다: {path}")
    token = path.read_text().strip()
    if len(token) < 16:
        raise RuntimeError(f"job-api 토큰이 너무 짧다(16자 이상): {path}")
    return token


def require_token(request: Request) -> None:
    expected: str = request.app.state.token
    header = request.headers.get("authorization", "")
    scheme, _, given = header.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(given.strip(), expected):
        raise ApiError(401, "unauthorized", "내부 토큰이 없거나 틀렸다")
