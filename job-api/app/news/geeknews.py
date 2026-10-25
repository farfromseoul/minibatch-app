"""GeekNews 읽기 (아키텍처 D40). 공식 RSS(Atom)와, 평가할 후보의 글 페이지 하나씩만 읽는다.

이용약관(2026-10-25 확인)은 '과도한 부하를 주는 자동화 접근'을 금지한다 → RSS 는 하루 1~2번, 글 페이지는 후보마다 한 번,
요청 사이에 쉰다. robots.txt Content-Signal: ai-input=yes, ai-train=no → LLM 입력으로만 쓴다.
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Optional

FEED_URL = "https://news.hada.io/rss/news"
ATOM = {"a": "http://www.w3.org/2005/Atom"}
TOPIC_ID = re.compile(r"news\.hada\.io/topic\?id=(\d+)")
TITLE_LINK = re.compile(r"<a[^>]+href=['\"]([^'\"]+)['\"][^>]*class=['\"][^'\"]*topic-title-link")
TAG = re.compile(r"<[^>]+>")


def topic_id(url: str) -> Optional[str]:
    m = TOPIC_ID.search(url or "")
    return m.group(1) if m else None


def topic_url(tid: str) -> str:
    return f"https://news.hada.io/topic?id={tid}"


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", fragment or ""))).strip()


def parse_feed(xml_text: str) -> list[dict[str, Any]]:
    """[{id, title, url, published(UTC, 시간대 없음), summary}]"""
    out = []
    for e in ET.fromstring(xml_text).findall("a:entry", ATOM):
        link = e.find("a:link", ATOM)
        url = link.get("href") if link is not None else ""
        tid = topic_id(url)
        if not tid:
            continue
        published = None
        raw = (e.findtext("a:published", default="", namespaces=ATOM) or "").strip()
        if raw:
            try:
                published = datetime.fromisoformat(raw).astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                published = None
        out.append({"id": tid, "title": (e.findtext("a:title", default="", namespaces=ATOM) or "").strip(),
                    "url": topic_url(tid), "published": published,
                    "summary": text_of(e.findtext("a:content", default="", namespaces=ATOM) or "")})
    return out


def parse_topic(page: str, tid: str) -> dict[str, Any]:
    """글 페이지에서 원문 링크와 추천 수 (없으면 None)"""
    m = TITLE_LINK.search(page)
    source = html.unescape(m.group(1)) if m else None
    if source and (source.startswith("/") or "news.hada.io" in source):
        source = None  # Ask·Show 처럼 원문이 GeekNews 안에 있는 글
    p = re.search(rf"id=['\"]tp{tid}['\"][^>]*>\s*(\d+)", page)
    return {"source": source, "points": int(p.group(1)) if p else None}
