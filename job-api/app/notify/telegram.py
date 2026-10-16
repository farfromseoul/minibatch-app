"""텔레그램 봇 연결부 (아키텍처 D28). Bot API 를 httpx 로 직접 부른다.

나가는 연결만 쓴다: 보내기(sendMessage)와 버튼 응답 가져오기(getUpdates). 웹훅을 쓰지 않아 MacBook 을 인터넷에 열지 않는다.
봇 토큰은 주소에 들어가므로 오류 메시지·로그에 주소를 남기지 않는다.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import httpx

log = logging.getLogger("job-api.telegram")


class TelegramError(Exception):
    pass


class TelegramBot:
    def __init__(self, token: str, chat_id: str, http: Optional[httpx.Client] = None):
        self._base = f"https://api.telegram.org/bot{token}"
        self.chat_id = str(chat_id)
        self._http = http or httpx.Client(timeout=60)

    @classmethod
    def from_settings(cls, settings) -> Optional["TelegramBot"]:
        """토큰 파일이나 chat id 가 없으면 None (텔레그램 승인만 꺼지고 서버는 뜬다)"""
        path = Path(settings.telegram_token_file)
        if not settings.telegram_chat_id or not path.is_file():
            log.info("텔레그램 승인 꺼짐: 토큰 파일 또는 chat id 없음")
            return None
        token = path.read_text(encoding="utf-8").strip()
        return cls(token, settings.telegram_chat_id) if token else None

    def _call(self, method: str, body: dict[str, Any], timeout: float = 15) -> Any:
        try:
            res = self._http.post(f"{self._base}/{method}", json=body, timeout=timeout)
        except httpx.HTTPError as e:
            raise TelegramError(f"{method} 연결 실패: {type(e).__name__}") from None  # 주소(토큰)를 남기지 않는다
        data = res.json() if res.content else {}
        if res.status_code != 200 or not data.get("ok"):
            raise TelegramError(f"{method} {res.status_code} {str(data.get('description', ''))[:200]}")
        return data.get("result")

    def send(self, text: str, buttons: Optional[list[tuple[str, str]]] = None) -> Any:
        body: dict[str, Any] = {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}
        if buttons:
            body["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in buttons]]}
        return self._call("sendMessage", body)

    def get_updates(self, offset: int, timeout: int = 30) -> list[dict[str, Any]]:
        return self._call("getUpdates", {"offset": offset, "timeout": timeout, "allowed_updates": ["callback_query"]},
                          timeout=timeout + 15) or []

    def answer(self, callback_id: str, text: str) -> None:
        self._call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:190]})

    def edit(self, chat_id: str, message_id: int, text: str) -> None:
        """처리한 메시지를 결과로 바꾸고 버튼을 없앤다 (reply_markup 을 보내지 않으면 버튼이 사라진다)"""
        self._call("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text[:4000],
                                       "disable_web_page_preview": True})
