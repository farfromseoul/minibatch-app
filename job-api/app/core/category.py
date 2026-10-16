"""카테고리 설정 묶음 읽기 (아키텍처 D23). content/categories/<키>.yaml"""
from __future__ import annotations

from typing import Any

import yaml

from app.pipeline.steps.base import StepFailure


def load_category(settings, key: str) -> dict[str, Any]:
    path = settings.category_file(key)
    if not path.is_file():
        raise StepFailure("deterministic", f"카테고리 설정이 없다: {key}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
