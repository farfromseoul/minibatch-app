"""원문 읽기 (아키텍처 D40). 사용자가 아닌 외부 사이트 주소를 서버가 대신 여는 일이라 SSRF 를 막는다.

- http(s) 만, 기본 포트(80·443)만
- 주소의 호스트를 DNS 로 풀어 사설·루프백·링크 로컬·예약 대역이면 거절. 리디렉션은 자동으로 따르지 않고 한 번씩 같은 검사
- 2MB·HTML 만 읽고, 본문(문단·제목·목록)만 글자로 추린다. 원문 전문은 DB 에 두지 않는다
"""
from __future__ import annotations

import ipaddress
import socket
from html.parser import HTMLParser
from typing import Callable, Optional
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 4
UA = "Mozilla/5.0 (compatible; MiniBatch-news/1.0; +https://news.hada.io)"


def resolve_host(host: str) -> list[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


def safe_url(url: str, resolve: Callable[[str], list[str]]) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.port not in (None, 80, 443):
        return False
    try:
        addrs = resolve(parts.hostname)
    except OSError:
        return False
    if not addrs:
        return False
    for a in addrs:
        ip = ipaddress.ip_address(a)
        if not ip.is_global or ip.is_multicast:
            return False
    return True


def fetch(url: str, http: httpx.Client, resolve: Callable[[str], list[str]]) -> Optional[str]:
    """검사를 통과한 주소만 연다. 실패하면 None"""
    for _ in range(MAX_REDIRECTS + 1):
        if not safe_url(url, resolve):
            return None
        try:
            res = http.get(url, headers={"User-Agent": UA}, follow_redirects=False, timeout=20)
        except httpx.HTTPError:
            return None
        if res.status_code in (301, 302, 303, 307, 308) and res.headers.get("location"):
            url = urljoin(url, res.headers["location"])
            continue
        ctype = res.headers.get("content-type", "")
        if res.status_code != 200 or ("html" not in ctype and "xml" not in ctype) or len(res.content) > MAX_BYTES:
            return None
        return res.text
    return None


class _Text(HTMLParser):
    KEEP = {"p", "h1", "h2", "h3", "li", "pre", "blockquote"}
    SKIP = {"script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.keep = 0
        self.parts: list[str] = []
        self.cur: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.KEEP:
            self.keep += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.KEEP and self.keep:
            self.keep -= 1
            text = " ".join("".join(self.cur).split())
            if text:
                self.parts.append(text)
            self.cur = []

    def handle_data(self, data):
        if self.keep and not self.skip:
            self.cur.append(data)


def html_to_text(page: str, limit: int = 12000) -> str:
    p = _Text()
    p.feed(page)
    return "\n".join(p.parts)[:limit]


def fetch_text(url: str, http: httpx.Client, resolve: Callable[[str], list[str]]) -> Optional[str]:
    page = fetch(url, http, resolve)
    if page is None:
        return None
    text = html_to_text(page)
    return text if len(text) >= 40 else None
