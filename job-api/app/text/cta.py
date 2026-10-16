"""시리즈 끝 안내 (아키텍처 D26). 문구는 카테고리 파일 series.cta_next·cta_end 에서 운영자가 정한다.

여러 문구를 적으면 화 번호로 돌려 쓴다. {next_title}·{series_title} 자리를 채운다.
"""
from __future__ import annotations

from typing import Any, Optional

DEFAULT_NEXT = ["다음 이야기가 궁금하시면 이어지는 영상을 확인해 주세요."]
DEFAULT_END = ["{series_title} 시리즈를 끝까지 봐 주셔서 고맙습니다."]


def outro_for(category: dict[str, Any], series: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """{line, title, subtitle} 또는 None(단독 영상)"""
    if not series:
        return None
    conf = category.get("series") or {}
    has_next = bool(series.get("nextTitle"))
    phrases = [p for p in (conf.get("cta_next") if has_next else conf.get("cta_end")) or [] if str(p).strip()]
    phrases = phrases or (DEFAULT_NEXT if has_next else DEFAULT_END)
    template = str(phrases[(series["episode"] - 1) % len(phrases)])
    line = template.replace("{next_title}", series.get("nextTitle") or "").replace("{series_title}", series["title"])
    if has_next:
        return {"line": line, "title": "다음 화", "subtitle": series["nextTitle"]}
    return {"line": line, "title": "끝", "subtitle": series["title"]}
