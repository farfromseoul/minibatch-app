"""텔레그램으로 승인받기 (아키텍처 D28).

- 작업이 검토 대기(REVIEW)가 되면 [승인(공개)][반려] 버튼을 단 메시지를 보낸다.
- 시리즈 계획을 LLM 이 만들면 [계획 승인] 버튼을 단 메시지를 보낸다.
- getUpdates 로 버튼 응답을 가져와 API 와 같은 규칙으로 처리한다(화 순서 승인, 승인 기록 검사는 그대로).
  정한 chat id 에서 온 응답만 처리한다.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from sqlalchemy import select

from app.core.errors import ApiError
from app.db.models import Episode, Job, Publication, Series
from app.domain import generation, review
from app.publish.approve import approve_and_publish

from .telegram import TelegramBot, TelegramError

log = logging.getLogger("job-api.telegram")
WHO = "텔레그램"


class TelegramApprovals:
    def __init__(self, bot: TelegramBot, *, settings, db: Callable, clock: Callable, youtube_factory: Callable):
        self.bot = bot
        self.settings, self.db, self.clock, self.youtube_factory = settings, db, clock, youtube_factory
        self.offset = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------- 보내기

    def _safe_send(self, text: str, buttons) -> None:
        try:
            self.bot.send(text, buttons)
        except TelegramError as e:  # 알림이 실패해도 제작은 계속된다 (n8n 검토 폼으로도 승인할 수 있다)
            log.warning("텔레그램 보내기 실패: %s", e)

    def notify_review(self, job_id: str) -> None:
        with self.db() as s:
            job = s.get(Job, job_id)
            if job is None or job.status != "REVIEW":
                return
            pub = s.get(Publication, job_id)
            head = f"{job.episode_number}화 " if job.series_id else ""
            series = s.get(Series, job.series_id) if job.series_id else None
            lines = [f"🎬 검토 대기: {head}{job.topic}"]
            if series is not None:
                lines.append(f"시리즈: {series.title}")
            lines.append(f"영상(비공개): https://www.youtube.com/shorts/{pub.video_id}" if pub and pub.video_id else "영상: 업로드 전")
            lines.append("승인하면 바로 공개됩니다.")
            text = "\n".join(lines)
        self._safe_send(text, [("승인(공개)", f"a:{job_id}"), ("반려", f"r:{job_id}")])

    def notify_plan(self, series_id: str) -> None:
        with self.db() as s:
            series = s.get(Series, series_id)
            if series is None or series.status != "PROPOSED":
                return
            eps = s.scalars(select(Episode).where(Episode.series_id == series_id).order_by(Episode.number)).all()
            text = "\n".join([f"📝 새 시리즈 계획 승인 필요: {series.title}", str((series.bible or {}).get("premise", ""))]
                             + [f"{e.number}. {e.title}" for e in eps])
        self._safe_send(text, [("계획 승인", f"p:{series_id}")])

    # ---------- 버튼 응답

    def poll_once(self, timeout: int = 30) -> None:
        for u in self.bot.get_updates(self.offset, timeout):
            self.offset = max(self.offset, int(u["update_id"]) + 1)
            cq = u.get("callback_query")
            if cq:
                self._handle(cq)

    def _handle(self, cq: dict[str, Any]) -> None:
        msg = cq.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id", ""))
        if chat != self.bot.chat_id or str((cq.get("from") or {}).get("id", "")) != self.bot.chat_id:
            self._try(self.bot.answer, cq["id"], "권한 없는 대화라 처리하지 않았습니다")
            return
        kind, _, target = str(cq.get("data", "")).partition(":")
        try:
            result = self._apply(kind, target)
        except ApiError as e:
            result = f"처리하지 못함: {e.message}"
        except Exception as e:  # 버튼 하나의 실패가 받기 루프를 멈추지 않게
            log.exception("텔레그램 버튼 처리 실패")
            result = f"처리하지 못함: {type(e).__name__}"
        self._try(self.bot.answer, cq["id"], result)
        self._try(self.bot.edit, chat, msg.get("message_id"), result)

    def _apply(self, kind: str, target: str) -> str:
        now = self.clock()
        with self.db() as s:
            if kind in ("a", "r"):
                job = s.get(Job, target)
                if job is None:
                    return f"작업이 없습니다: {target}"
                head = f"{job.episode_number}화 {job.topic}" if job.series_id else job.topic
                if kind == "r":
                    review.reject(s, job, now, WHO, "텔레그램에서 반려")
                    s.commit()
                    return f"❌ 반려: {head}"
                pub = approve_and_publish(s, self.settings, job, now, WHO, None, self.youtube_factory)
                if pub.get("ok"):
                    return f"✅ 승인 → {pub['status']}: {head}" + (f"\n(경고: {'; '.join(pub['warnings'])})" if pub.get("warnings") else "")
                return f"✅ 승인됨, 공개는 안 됨({pub.get('skipped') or pub.get('kind')}): {head}. n8n 검토 폼이나 POST /publish 로 다시"
            if kind == "p":
                series = s.get(Series, target)
                if series is None:
                    return f"시리즈가 없습니다: {target}"
                generation.approve_series_plan(s, series, now, None, None)
                s.commit()
                return f"✅ 계획 승인: {series.title} (다음 생산 일정부터 1화씩)"
        return f"모르는 버튼: {kind}"

    @staticmethod
    def _try(fn, *args) -> None:
        try:
            fn(*args)
        except TelegramError as e:
            log.warning("텔레그램 응답 실패: %s", e)

    # ---------- 실제 서버: 받기 루프

    def start(self) -> None:
        def loop():
            while not self._stop.is_set():
                try:
                    self.poll_once(timeout=30)
                except Exception as e:
                    log.warning("텔레그램 받기 실패, 10초 뒤 다시: %s", e)
                    self._stop.wait(10)
        self._thread = threading.Thread(target=loop, name="telegram", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
