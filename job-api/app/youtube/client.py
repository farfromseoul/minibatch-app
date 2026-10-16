"""YouTube Data API v3 연결부 (앱 설계 "YouTube 게시", 아키텍처 D9·D26).

2026-10-16 손 업로드(실행계획 15·15-b)에서 확인한 흐름을 코드로 옮겼다.
- 인증: 갱신 토큰으로 access token 을 받아 메모리에만 둔다(파일에 쓰지 않는다). 범위는 `youtube` 하나.
- 업로드: 재개 가능한 업로드. POST 로 세션 주소를 받고, 그 주소에 파일을 PUT 한다.
- 실패 종류: 할당량 → quota, 연결·시간 초과·429·5xx → transient, 그 밖의 4xx·토큰 만료 → deterministic.
토큰·클라이언트 비밀·Google 원문 응답은 오류 메시지에 넣지 않는다.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
QUOTA_REASONS = {"quotaExceeded", "uploadLimitExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded"}
DESCRIPTION_MAX_BYTES = 5000  # YouTube 설명란 한도
TITLE_MAX_CHARS = 100


class YouTubeError(Exception):
    def __init__(self, kind: str, message: str, status: Optional[int] = None, reason: Optional[str] = None):
        super().__init__(message)
        self.kind = kind  # transient | deterministic | quota (단계 실패 종류와 같다)
        self.message = message
        self.status = status
        self.reason = reason


def _clean(text: str) -> str:
    return text.replace("<", "").replace(">", "")  # 제목·설명에 < > 가 있으면 YouTube 가 요청을 거절한다


def clean_title(title: str) -> str:
    return _clean(title).strip()[:TITLE_MAX_CHARS]


def with_disclosure(description: str, disclosure: str) -> str:
    """설명 끝에 고지 문구를 줄을 바꿔 한 번만 붙인다. 길면 본문을 잘라 고지 문구를 지킨다 (Supertonic 라이선스, 06 R26)"""
    body = _clean(description).rstrip()
    if body.endswith(disclosure):
        body = body[: -len(disclosure)].rstrip()
    tail = f"\n\n{disclosure}"
    room = DESCRIPTION_MAX_BYTES - len(tail.encode("utf-8"))
    encoded = body.encode("utf-8")
    if len(encoded) > room:
        body = encoded[:room].decode("utf-8", errors="ignore").rstrip()
    return f"{body}{tail}" if body else disclosure


class YouTube:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str,
                 http: Optional[httpx.Client] = None, timeout: float = 120.0):
        self.client_id = client_id
        self._client_secret = client_secret
        self.refresh_token = refresh_token
        self._http = http or httpx.Client(timeout=timeout)
        self._access: Optional[str] = None
        self._expires = 0.0

    @classmethod
    def from_files(cls, client_file: Path, token_file: Path, **kw) -> "YouTube":
        """클라이언트 파일(데스크톱 앱, `installed`)과 15번에서 저장한 토큰 파일을 읽는다"""
        try:
            client = json.loads(Path(client_file).read_text(encoding="utf-8"))["installed"]
            token = json.loads(Path(token_file).read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError) as e:
            raise YouTubeError("deterministic", f"YouTube 인증 파일을 읽지 못했다({type(e).__name__}): "
                                                f"실행계획 15번으로 갱신 토큰을 발급한다") from e
        if not token.get("refresh_token"):
            raise YouTubeError("deterministic", "토큰 파일에 refresh_token 이 없다: 실행계획 15번 ②~④로 다시 발급한다")
        return cls(client["client_id"], client["client_secret"], token["refresh_token"], **kw)

    @classmethod
    def from_settings(cls, settings) -> "YouTube":
        return cls.from_files(settings.youtube_client_file, settings.youtube_token_file)

    # ---------- 인증

    def _token(self, force: bool = False) -> str:
        if self._access and not force and time.monotonic() < self._expires:
            return self._access
        try:
            res = self._http.post(TOKEN_URL, data={"client_id": self.client_id, "client_secret": self._client_secret,
                                                   "refresh_token": self.refresh_token, "grant_type": "refresh_token"})
        except httpx.HTTPError as e:
            raise YouTubeError("transient", f"토큰 갱신 연결 실패: {type(e).__name__}") from e
        if res.status_code >= 500:
            raise YouTubeError("transient", f"토큰 갱신 {res.status_code}", status=res.status_code)
        body = res.json() if res.content else {}
        if res.status_code != 200 or "access_token" not in body:
            err = body.get("error", res.status_code)
            raise YouTubeError("deterministic", f"갱신 토큰을 쓸 수 없다({err}). 동의 화면이 테스트 상태면 7일 뒤 만료된다: "
                                                f"실행계획 15번 ②~④로 다시 발급한다", status=res.status_code, reason=str(err))
        self._access = body["access_token"]
        self._expires = time.monotonic() + max(60, int(body.get("expires_in", 3600)) - 60)
        return self._access

    def _send(self, method: str, url: str, what: str, **kw) -> httpx.Response:
        headers = kw.pop("headers", {})
        for attempt in (1, 2):
            try:
                res = self._http.request(method, url, headers={**headers, "Authorization": f"Bearer {self._token(attempt == 2)}"}, **kw)
            except httpx.TimeoutException as e:
                raise YouTubeError("transient", f"{what} 시간 초과") from e
            except httpx.HTTPError as e:
                raise YouTubeError("transient", f"{what} 연결 실패: {type(e).__name__}") from e
            if res.status_code == 401 and attempt == 1:
                continue  # access token 이 만료됐을 수 있다. 한 번만 새로 받아 다시 한다
            break
        if res.status_code < 400:
            return res
        reason, message = None, ""
        try:
            err = res.json().get("error", {})
            message = str(err.get("message", ""))[:200]
            reason = (err.get("errors") or [{}])[0].get("reason")
        except ValueError:
            pass
        detail = f"{what} {res.status_code} {reason or ''} {message}".strip()
        if reason in QUOTA_REASONS:  # 상태 코드는 403·400 둘 다 온다 (채널 업로드 한도는 400, 2026-10-16 실제)
            raise YouTubeError("quota", detail, res.status_code, reason)
        if res.status_code == 429 or res.status_code >= 500:
            raise YouTubeError("transient", detail, res.status_code, reason)
        raise YouTubeError("deterministic", detail, res.status_code, reason)

    # ---------- 영상

    def upload_video(self, path: Path, *, title: str, description: str, disclosure: str, category_id: str,
                     tags: list[str], synthetic: bool) -> dict[str, Any]:
        """비공개로 올린다. 고지 문구는 여기서 붙여 호출하는 쪽이 빠뜨릴 수 없게 한다 (앱 설계 2026-10-16 결정)"""
        if not disclosure or not disclosure.strip():
            raise ValueError("고지 문구가 비어 있다 (카테고리 youtube.disclosure)")
        path = Path(path)
        meta = {"snippet": {"title": clean_title(title), "description": with_disclosure(description, disclosure.strip()),
                            "categoryId": category_id, "tags": [_clean(t) for t in tags][:15]},
                "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                           "containsSyntheticMedia": bool(synthetic)}}
        init = self._send("POST", UPLOAD, "업로드 세션", params={"uploadType": "resumable", "part": "snippet,status"},
                          headers={"Content-Type": "application/json; charset=UTF-8",
                                   "X-Upload-Content-Length": str(path.stat().st_size),
                                   "X-Upload-Content-Type": "video/mp4"},
                          content=json.dumps(meta, ensure_ascii=False).encode("utf-8"))
        session = init.headers.get("Location")
        if not session:
            raise YouTubeError("transient", "업로드 세션 주소(Location)가 없다")
        with path.open("rb") as fh:
            res = self._send("PUT", session, "영상 업로드", headers={"Content-Type": "video/mp4"}, content=fh.read())
        return res.json()

    def set_privacy(self, video_id: str, privacy: str, publish_at: Optional[datetime] = None) -> dict[str, Any]:
        """public 이면 바로 공개, private + publish_at 이면 예약 공개 (비공개이고 공개된 적 없는 영상만 된다).

        status 를 바꿀 때 보내지 않은 값은 지워진다(공식 문서, 2026-10-16 조회). 그래서 지금 값을 읽어 함께 보낸다.
        selfDeclaredMadeForKids·containsSyntheticMedia 는 보낼 때만 바뀌므로 업로드 때 값을 그대로 둔다.
        """
        res = self._send("GET", f"{API}/videos", "영상 조회", params={"part": "status", "id": video_id})
        items = res.json().get("items") or []
        if not items:
            raise YouTubeError("deterministic", f"영상이 없다: {video_id}")
        current = items[0].get("status", {})
        status: dict[str, Any] = {k: current[k] for k in ("license", "embeddable", "publicStatsViewable") if k in current}
        status["privacyStatus"] = privacy
        if publish_at is not None:
            utc = publish_at if publish_at.tzinfo is None else publish_at.astimezone(timezone.utc).replace(tzinfo=None)
            status["publishAt"] = utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        res = self._send("PUT", f"{API}/videos", "공개 범위 변경", params={"part": "status"},
                         json={"id": video_id, "status": status})
        return res.json()

    def append_to_description(self, video_id: str, text: str, disclosure: str) -> bool:
        """설명란의 고지 문구 바로 앞에 text 를 더한다. 이미 있으면 하지 않는다 (D26 ④ 앞 화에 다음 화 링크)"""
        res = self._send("GET", f"{API}/videos", "영상 조회", params={"part": "snippet", "id": video_id})
        items = res.json().get("items") or []
        if not items:
            raise YouTubeError("deterministic", f"영상이 없다: {video_id}")
        snippet = items[0]["snippet"]
        desc = snippet.get("description", "")
        if text in desc:
            return False
        body = desc.rstrip()
        if body.endswith(disclosure):
            body = body[: -len(disclosure)].rstrip()
        new = {"title": snippet["title"], "categoryId": snippet["categoryId"],
               "description": with_disclosure(f"{body}\n\n{text}" if body else text, disclosure)}
        if snippet.get("tags"):
            new["tags"] = snippet["tags"]
        self._send("PUT", f"{API}/videos", "설명란 수정", params={"part": "snippet"}, json={"id": video_id, "snippet": new})
        return True

    # ---------- 재생목록 (D26 ②)

    def create_playlist(self, title: str, description: str, privacy: str = "public") -> str:
        """시리즈 재생목록. 공개로 만든다: 비공개 영상은 공개 재생목록에서도 다른 사람에게 보이지 않는다"""
        res = self._send("POST", f"{API}/playlists", "재생목록 만들기", params={"part": "snippet,status"},
                         json={"snippet": {"title": clean_title(title), "description": _clean(description)[:5000]},
                               "status": {"privacyStatus": privacy}})
        return res.json()["id"]

    def playlist_video_ids(self, playlist_id: str) -> list[str]:
        ids, token = [], None
        while True:
            params = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": 50}
            if token:
                params["pageToken"] = token
            body = self._send("GET", f"{API}/playlistItems", "재생목록 조회", params=params).json()
            ids += [i["contentDetails"]["videoId"] for i in body.get("items", [])]
            token = body.get("nextPageToken")
            if not token:
                return ids

    def add_to_playlist(self, playlist_id: str, video_id: str) -> bool:
        """끝에 넣는다. 이미 있으면 넣지 않는다(재시도 대비). 화는 앞 화 승인 뒤에 만들어지므로 끝에 넣으면 화 순서다 (D24)"""
        if video_id in self.playlist_video_ids(playlist_id):
            return False
        self._send("POST", f"{API}/playlistItems", "재생목록에 넣기", params={"part": "snippet"},
                   json={"snippet": {"playlistId": playlist_id,
                                     "resourceId": {"kind": "youtube#video", "videoId": video_id}}})
        return True
