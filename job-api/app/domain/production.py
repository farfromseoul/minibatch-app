"""지금 생산 (2026-10-31 사용자: 텔레그램으로 n8n 1번을 정각을 기다리지 않고 시작).

job-api 가 n8n 1번 워크플로의 웹훅(`MINIBATCH_PRODUCE_WEBHOOK_URL`, compose 내부망)을 부른다. 1번 워크플로가 이미 돌고 있으면
부르지 않는다: 같은 작업을 두 실행이 함께 밀면 409(busy)와 재시도가 꼬인다.
'돌고 있다' = 단계가 실행 중이거나, 1번 워크플로만 부르는 요청(/jobs/next, 단계 실행, 되돌리기)이 최근 ACTIVE_SEC 안에 있었다.
1번 워크플로는 단계 사이에 5~60초 간격으로 다시 부르므로(decide.mjs) 90초면 실행 중인 흐름을 놓치지 않는다.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

import httpx

log = logging.getLogger("job-api.production")
ACTIVE_SEC = 90


class Production:
    def __init__(self, *, url: str, clock: Callable[[], datetime], runner_busy: Callable[[], Optional[str]]):
        self.url = url
        self.clock = clock
        self.runner_busy = runner_busy                  # 실행 중인 단계 설명 또는 None
        self.post: Callable[..., Any] = httpx.post      # 테스트에서 바꿔 끼운다
        self._seen: Optional[datetime] = None
        self._lock = threading.Lock()

    def touch(self) -> None:
        """1번 워크플로가 다녀갔다 (/jobs/next, 단계 실행, 되돌리기)"""
        with self._lock:
            self._seen = self.clock()

    def busy(self) -> Optional[str]:
        running = self.runner_busy()
        if running:
            return f"단계 실행 중: {running}"
        with self._lock:
            seen = self._seen
        if seen is not None and self.clock() - seen < timedelta(seconds=ACTIVE_SEC):
            return f"1번 워크플로가 {int((self.clock() - seen).total_seconds())}초 전에 다녀갔다"
        return None

    def run(self) -> dict[str, Any]:
        """{started, message}. 이미 돌고 있으면 시작하지 않는다"""
        why = self.busy()
        if why:
            return {"started": False, "message": f"⏳ 이미 생산 중입니다 ({why}). 끝나면 다음 작업도 이어서 만듭니다. 진행은 /status"}
        try:
            res = self.post(self.url, timeout=10)
        except httpx.HTTPError as e:
            log.warning("생산 웹훅 실패: %s", e)
            return {"started": False, "message": f"⚠️ n8n 1번을 부르지 못했습니다({type(e).__name__}). n8n 이 떠 있는지 확인해 주세요"}
        if res.status_code >= 400:
            return {"started": False,
                    "message": f"⚠️ n8n 1번이 거절했습니다({res.status_code}). 1번 워크플로가 게시(활성)돼 있는지 확인해 주세요"}
        self.touch()  # 바로 다시 눌러도 두 번 시작하지 않게
        return {"started": True, "message": "▶ 생산을 시작했습니다(n8n 1번). 이어 할 작업부터, 없으면 새 작업을 만듭니다. 진행은 /status"}
