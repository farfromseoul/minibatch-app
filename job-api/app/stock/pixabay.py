"""Pixabay 스톡 영상 (2026-10-17, 레터박스 스타일 가운데 판).

API 규칙(공식 문서 2026-10-17): 무료, 출처 표시, 같은 검색 24시간 캐시, 받아서 우리 쪽에 저장(영구 링크 금지),
대량 다운로드 금지. 라이선스: 출처 표기 의무 없음, 알아볼 수 있는 인물을 부도덕하게 쓰지 않는다.
기본 User-Agent(python)는 Cloudflare 가 막아서(오류 1010) 우리 User-Agent 를 보낸다. 키는 로그·캐시에 남기지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import httpx

API = "https://pixabay.com/api/videos/"
UA = "minibatch-job-api/1.0 (+https://github.com/farfromseoul/minibatch-app)"
CACHE_SEC = 24 * 3600
MAX_BYTES = 40_000_000


class StockError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind  # transient | deterministic
        self.message = message


@dataclass
class Clip:
    id: int
    url: str
    width: int
    height: int
    duration: float
    user: str
    page: str


class Pixabay:
    def __init__(self, key: str, cache_dir: Path, http: Optional[httpx.Client] = None, now: Callable[[], float] = time.time):
        self._key = key
        self.cache_dir = Path(cache_dir)
        self._http = http or httpx.Client(timeout=60, headers={"User-Agent": UA}, follow_redirects=True)
        self._now = now

    @classmethod
    def from_settings(cls, settings, cfg: dict) -> "Pixabay":
        path = Path(cfg.get("api_key_file", "/run/minibatch/providers/pixabay_api_key"))
        try:
            key = path.read_text(encoding="utf-8").strip()
        except OSError as e:
            raise StockError("deterministic", f"Pixabay 키 파일을 읽지 못했다: {path}") from e
        return cls(key, settings.data_dir / "cache" / "pixabay")

    def _get(self, url: str, **kw) -> httpx.Response:
        try:
            res = self._http.get(url, headers={"User-Agent": UA}, **kw)
        except httpx.HTTPError as e:
            raise StockError("transient", f"Pixabay 연결 실패: {type(e).__name__}") from None  # 주소에 키가 있어 남기지 않는다
        if res.status_code == 429 or res.status_code >= 500:
            raise StockError("transient", f"Pixabay {res.status_code}")
        if res.status_code != 200:
            raise StockError("deterministic", f"Pixabay {res.status_code}")
        return res

    def _hits(self, query: str) -> list[dict]:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / (hashlib.sha256(query.lower().encode()).hexdigest()[:24] + ".json")
        if path.is_file():
            cached = json.loads(path.read_text(encoding="utf-8"))
            if self._now() - cached["at"] < CACHE_SEC:
                return cached["hits"]
        params = {"key": self._key, "q": query, "video_type": "film", "safesearch": "true", "min_width": 1280, "per_page": 20}
        hits = self._get(API, params=params).json().get("hits", [])
        path.write_text(json.dumps({"at": self._now(), "query": query, "hits": hits}, ensure_ascii=False), encoding="utf-8")
        return hits

    def search(self, query: str, min_seconds: float) -> list[Clip]:
        """저품질·폭 1280 미만은 뺀다. 장면 길이 이상인 것을 앞에(나머지는 반복 재생), 그 안에서는 Pixabay 관련도 순.
        2026-10-17: 다운로드 수로 다시 정렬했더니 'robot arm factory' 에 굴뚝 공장이 골라져 관련도 순으로 바꿨다"""
        clips = []
        for h in self._hits(query):
            v = (h.get("videos") or {}).get("medium") or {}
            if h.get("isLowQuality") or int(v.get("width") or 0) < 1280 or not v.get("url"):
                continue
            clips.append((h, Clip(id=int(h["id"]), url=v["url"], width=int(v["width"]), height=int(v["height"]),
                                  duration=float(h.get("duration") or 0), user=str(h.get("user", "")), page=str(h.get("pageURL", "")))))
        words = {w for w in query.lower().split() if len(w) > 2}

        def matched(h: dict) -> int:  # 태그에 검색어 단어가 몇 개 들어 있나 (관련도만으로는 엉뚱한 영상이 골라졌다)
            tags = str(h.get("tags", "")).lower()
            return sum(1 for w in words if w in tags)

        # 장면 길이 이상 → 태그 일치 많은 것 → API 관련도 순 (안정 정렬)
        clips.sort(key=lambda hc: (hc[1].duration < min_seconds, -matched(hc[0])))
        return [c for _, c in clips]

    def download(self, clip: Clip, dest: Path) -> None:
        res = self._get(clip.url)
        if len(res.content) > MAX_BYTES:
            raise StockError("deterministic", f"영상이 너무 크다: {len(res.content)} 바이트")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        tmp.write_bytes(res.content)
        tmp.replace(dest)
