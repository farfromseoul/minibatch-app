"""텔레그램으로 승인받기 (아키텍처 D28).

- 작업이 검토 대기(REVIEW)가 되면 [승인(공개)][반려] 버튼을 단 메시지를 보낸다.
- 시리즈 계획을 LLM 이 만들면 [계획 승인] 버튼을 단 메시지를 보낸다.
- getUpdates 로 버튼 응답을 가져와 API 와 같은 규칙으로 처리한다(화 순서 승인, 승인 기록 검사는 그대로).
  정한 chat id 에서 온 응답만 처리한다.
- 규칙 때문에 처리하지 못한 버튼(화 순서 등)은 메시지·버튼을 그대로 두고 안내만 띄운다 (2026-10-19: 버튼이 지워져 다시 누를 수 없었다).
- 검토 대기가 6시간 넘게 남고 지금 승인할 수 있는 차례인 영상은 다시 알린다 (2026-10-19 사용자).
- 다음 시리즈 계획 전에 주제·화 수를 묻는다(D37). 답(`주제, 화수`), [자동으로 정하기], [오늘은 건너뛰기], `/series 주제, 화수`.
  묻는 상태는 데이터 폴더의 파일에 두어 재시작해도 이어진다. 답이 없으면 다음 날 다시 묻고, 계획은 저절로 만들지 않는다.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy import select

from app.core.errors import ApiError
from app.core.timeutil import kst_date
from app.db.models import Episode, Job, Publication, Series
from app.domain import cancel as cancel_domain, generation, jobs as jobs_domain, overview, review, series_order, stuck
from app.domain.status import EP_DONE
from app.publish.approve import approve_and_publish

from .telegram import TelegramBot, TelegramError

log = logging.getLogger("job-api.telegram")
WHO = "텔레그램"
REMIND_SEC = 6 * 3600  # 검토 대기 다시 알림 간격
MAX_REMIND = 5         # 한 번에 다시 보내는 최대 수
PLAN_REMIND_SEC = 24 * 3600  # 승인 대기 계획 다시 알림 간격
HELP = """🤖 MiniBatch 명령
/status — 현황: 시리즈 화별 상태, 다음 계획, IT 뉴스, ASMR, 오늘 업로드
/news — IT 뉴스 후보 받기 (GeekNews 새 글을 모아 평가해 보냄)
/news 더 — 아직 안 보낸 다음 후보
/news <GeekNews 글 주소> — 그 글을 평가해 후보로 보냄
/series 주제, 화수 — 다음 시리즈 계획 만들기 (화수 3~20, 빼면 10)
   다음 줄에 (선택) 참고 자료 주소(http…, 5개까지) · 화 제목('1.' 또는 '-' 로 시작, 주면 그 개수가 화 수)
   예) /series 클로드 코드 외부 스킬, 5
       https://github.com/anthropics/skills
       1. 스킬이란 무엇일까?
/top 주제, 개수 — 목록형 쇼츠 하나 만들기 (개수 3~5, 빼면 5. 다음 정각에 만든다)
   다음 줄에 (선택) 참고 자료 주소(http…, 5개까지) · 항목 이름('1.' 또는 '-' 로 시작, 주면 그 개수)
   예) /top 클로드 코드에서 진짜 쓸 기능, 5
       https://docs.anthropic.com/claude-code
/run — 지금 생산 (정각을 기다리지 않고 n8n 1번 실행. 이미 돌고 있으면 알려 줌)
/help — 이 도움말

버튼
· 영상 검토 대기: [승인(공개)] [반려] — 시리즈는 앞 화부터
· 시리즈 계획: [계획 승인] [다른 주제로]
· 다음 시리즈 주제 질문: [자동으로 정하기] [오늘은 건너뛰기] — 답장은 '주제, 화수'
· 대본이 3번 통과 못 함: [개요 고쳐 다시] [건너뛰기]
· 일시적 오류(시간 초과 등)로 멈춤: [다시 시도] [건너뛰기]
· IT 뉴스 후보: [이걸로 만들기] — 하루 기본 1편, 최대 3편
· ASMR: [업로드 승인] [공개 승인] [버리기]

자동으로 하는 일
· 생산: 06~23시 매시 정각 (n8n 1번), 언제든 /run
· IT 뉴스 후보: 매일 07:00 (n8n 7번)
· 다음 시리즈 주제 질문: 남은 화가 적으면 하루 한 번 (n8n 3번)
· ASMR inbox 확인: 매시 정각 (n8n 6번)
· 승인 대기 다시 알림: 검토 6시간, 계획·멈춘 작업 하루 한 번
· 상태 감시: 5분마다, Codex 3번 연속 실패 등 새 경고만 (n8n 4번)"""
DEFAULT_COUNT, MIN_COUNT, MAX_COUNT = 10, 3, 20  # 시리즈 화 수 (D37)
COUNT = re.compile(r"^(\d+)\s*(화|편)?$")
EXAMPLE = "예) 쿠버네티스 기초, 8"
TOP_DEFAULT, TOP_MIN, TOP_MAX = 5, 3, 5  # 목록형 쇼츠 항목 수 (D42)
TOP_EXAMPLE = "예) /top 개발자가 매일 쓰는 터미널 도구, 5"


MAX_REFERENCES = 5
EPISODE_LINE = re.compile(r"^\s*(?:\d+\s*[.)]|[-•*])\s*(.+)$")


@dataclass
class PlanRequest:
    theme: str
    count: int
    references: list[str] = field(default_factory=list)  # 참고 자료 주소 (선택)
    episodes: list[str] = field(default_factory=list)    # 화 제목 (선택, 주면 화 수 = 개수)


def parse_request(text: str, *, default: int = DEFAULT_COUNT, lo: int = MIN_COUNT, hi: int = MAX_COUNT,
                  unit: str = "화") -> PlanRequest:
    """첫 줄 '주제, 화수'(화수를 빼면 10). 다음 줄: http(s)… 는 참고 자료, '1.'·'2)'·'-' 로 시작하면 화 제목 (2026-10-30).
    주제 안의 쉼표는 마지막 쉼표 뒤가 숫자가 아니면 주제로 둔다. /top(D42)도 같은 모양: 개수 3~5, 줄은 항목 이름"""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        raise ValueError("주제가 비어 있습니다")
    first = lines[0]
    theme, sep, tail = first.replace("，", ",").rpartition(",")
    m = COUNT.match(tail.strip()) if sep else None
    theme, count = (theme.strip(), int(m.group(1))) if m else (first, default)
    refs, episodes = [], []
    for line in lines[1:]:
        if line.startswith(("http://", "https://")):
            refs.append(line.split()[0])
        elif (e := EPISODE_LINE.match(line)):
            episodes.append(e.group(1).strip()[:200])
        else:
            raise ValueError(f"알 수 없는 줄입니다: '{line[:30]}'. 참고 자료는 http 로, {unit} 제목은 '1.' 이나 '-' 로 시작합니다")
    if not theme:
        raise ValueError("주제가 비어 있습니다")
    if len(theme) > 100:
        raise ValueError("주제는 100자 이내로 써 주세요")
    if len(refs) > MAX_REFERENCES:
        raise ValueError(f"참고 자료는 {MAX_REFERENCES}개까지 줄 수 있습니다")
    if episodes:
        count = len(episodes)
    if not lo <= count <= hi:
        raise ValueError(f"{unit} 수는 {lo}~{hi} 사이로 써 주세요" + (f" ({unit} 제목 개수)" if episodes else ""))
    return PlanRequest(theme, count, refs, episodes)


class TelegramApprovals:
    def __init__(self, bot: TelegramBot, *, settings, db: Callable, clock: Callable, youtube_factory: Callable):
        self.bot = bot
        self.settings, self.db, self.clock, self.youtube_factory = settings, db, clock, youtube_factory
        self.offset = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._reminded: dict[str, Any] = {}  # 작업 → 마지막으로 다시 알린 시각 (재시작하면 비어 6시간 뒤부터 다시 센다)
        self._state_lock = threading.Lock()  # API(묻기)와 받기 루프(답)가 같은 상태 파일을 고친다
        self.runner = self.providers = None  # 계획 생성에 쓴다. 서버가 만든 뒤 attach 로 넣는다
        self.asmr = None  # ASMR 채널 버튼(ua·up·ux, D38). 서버가 만든 뒤 넣는다
        self.news = None  # IT 뉴스 후보·[이걸로](n:, D40). 서버가 만든 뒤 넣는다
        self.production = None  # /run: n8n 1번 지금 생산 (2026-10-31). 서버가 만든 뒤 넣는다
        # 몇 분 걸리는 일(/news 평가)을 받기 루프 밖에서 돌린다. 그동안에도 버튼·다시 알림이 처리된다 (2026-10-26)
        self.run_background: Callable[[Callable[[], None]], None] = (
            lambda fn: threading.Thread(target=fn, name="news", daemon=True).start())

    def attach(self, runner, providers) -> None:
        self.runner, self.providers = runner, providers

    # ---------- 보내기

    def _safe_send(self, text: str, buttons) -> None:
        try:
            self.bot.send(text, buttons)
        except TelegramError as e:  # 알림이 실패해도 제작은 계속된다 (n8n 검토 폼으로도 승인할 수 있다)
            log.warning("텔레그램 보내기 실패: %s", e)

    def notify_review(self, job_id: str, reminder: bool = False) -> None:
        with self.db() as s:
            job = s.get(Job, job_id)
            if job is None or job.status != "REVIEW":
                return
            pub = s.get(Publication, job_id)
            head = f"{job.episode_number}화 " if job.series_id else ""
            series = s.get(Series, job.series_id) if job.series_id else None
            lines = [("⏰ 다시 알림 · " if reminder else "") + f"🎬 검토 대기: {head}{job.topic}"]
            if series is not None:
                lines.append(f"시리즈: {series_order.label(s, series)}")  # 몇 번째 시리즈 (D33)
            lines.append(f"영상(비공개): https://www.youtube.com/shorts/{pub.video_id}" if pub and pub.video_id else "영상: 업로드 전")
            lines.append("승인하면 바로 공개됩니다.")
            text = "\n".join(lines)
        self._safe_send(text, [("승인(공개)", f"a:{job_id}"), ("반려", f"r:{job_id}")])

    def notify_plan(self, series_id: str, reminder: bool = False) -> None:
        with self.db() as s:
            series = s.get(Series, series_id)
            if series is None or series.status != "PROPOSED":
                return
            eps = s.scalars(select(Episode).where(Episode.series_id == series_id).order_by(Episode.number)).all()
            prev = series_order.previous(s)
            head = ("⏰ 다시 알림 · " if reminder else "") + f"📝 새 시리즈 계획 승인 필요 ({series_order.next_sequence(s)}번째 시리즈): {series.title}"
            after = [f"앞 시리즈: {series_order.label(s, prev)}"] if prev is not None else []
            text = "\n".join([head, *after, str((series.bible or {}).get("premise", ""))]
                             + [f"{e.number}. {e.title}" for e in eps])
        try:
            self.bot.send(text, [("계획 승인", f"p:{series_id}"), ("다른 주제로", f"pc:{series_id}")])
        except TelegramError as e:
            log.warning("텔레그램 보내기 실패: %s", e)
            return
        sent = self.clock().isoformat()  # 현황(/overview)에 "보냈는지"를 보여 주려고 남긴다
        self._edit_state(lambda st: st.setdefault("planSent", {}).__setitem__(series_id, sent))

    # ---------- 버튼 응답

    def poll_once(self, timeout: int = 30) -> None:
        for u in self.bot.get_updates(self.offset, timeout):
            self.offset = max(self.offset, int(u["update_id"]) + 1)
            cq = u.get("callback_query")
            if cq:
                self._handle(cq)
            elif u.get("message"):
                self._handle_message(u["message"])
        self.make_wanted_plan()
        if self.asmr is not None:  # [업로드 승인]을 누른 영상은 바로 올린다
            self.asmr.process_queue()

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
            # 규칙에 막힌 것(화 순서 등)은 나중에 같은 버튼을 다시 누를 수 있게 메시지·버튼을 그대로 둔다
            self._try(self.bot.answer, cq["id"], f"처리하지 못함: {e.message}")
            return
        except Exception as e:  # 버튼 하나의 실패가 받기 루프를 멈추지 않게
            log.exception("텔레그램 버튼 처리 실패")
            result = f"처리하지 못함: {type(e).__name__}"
        self._try(self.bot.answer, cq["id"], result)
        self._try(self.bot.edit, chat, msg.get("message_id"), result)

    def _apply(self, kind: str, target: str) -> str:
        if kind == "q":
            return self._question_button(target)
        if kind == "pc":
            return self._change_plan(target)
        if kind == "n":  # IT 뉴스 [이걸로] (D40)
            if self.news is None:
                return "IT 뉴스 기능이 꺼져 있습니다"
            return self.news.pick(target)
        if kind == "ro":
            return self._fix_outline(target)
        if kind == "rs":
            return self._skip_episode(target)
        if kind == "rt":
            return self._retry_failed(target)
        if kind in ("ua", "up", "ux"):  # ASMR 채널 (D38): 업로드 승인, 공개 승인, 버리기
            if self.asmr is None:
                return "ASMR 기능이 꺼져 있습니다"
            act = {"ua": self.asmr.approve_upload, "up": self.asmr.publish, "ux": self.asmr.reject}[kind]
            return act(target, WHO)
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

    # ---------- 다음 시리즈 주제 묻기 (D37)

    def _state_path(self) -> Path:
        return Path(self.settings.data_dir) / "telegram" / "series_request.json"

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self._state_path().read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}

    def _save(self, st: dict[str, Any]) -> None:
        path = self._state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)  # 쓰다 멈춰도 반쯤 쓴 파일이 남지 않게

    def _plan_waiting(self) -> bool:
        with self.db() as s:
            return s.scalar(select(Series.id).where(Series.status == "PROPOSED").limit(1)) is not None

    def ask_series(self, category: str, count: int = DEFAULT_COUNT) -> dict[str, Any]:
        """n8n 3번이 '계획이 필요하다'고 볼 때 부른다(매시). 하루에 한 번만 묻는다 (한국 날짜)"""
        if self._plan_waiting():
            return {"asked": False, "reason": "plan_pending"}
        today = kst_date(self.clock())
        with self._state_lock:
            st = self._load()
            if st.get("askedDate") == today:
                return {"asked": False, "reason": "asked_today"}
            self._send_question(category, count)
        return {"asked": True}

    def _send_question(self, category: str, count: int) -> None:
        """주제·화 수 질문을 보내고 '묻는 중'으로 적는다. _state_lock 안에서 부른다"""
        today = kst_date(self.clock())
        with self.db() as s:
            prev = series_order.previous(s)
            head = f"📝 다음 시리즈를 준비할 차례입니다 ({series_order.next_sequence(s)}번째 시리즈)."
            after = [f"앞 시리즈: {series_order.label(s, prev)}"] if prev is not None else []
        text = "\n".join([head, *after, f"주제와 화 수를 답장해 주세요. {EXAMPLE}",
                          f"화 수는 {MIN_COUNT}~{MAX_COUNT}(빼면 {DEFAULT_COUNT}). 다음 줄에 참고 자료 주소(http…)나 화 제목('1.', '-')을 더할 수 있습니다.",
                          "언제든 /series 주제, 화수 로도 만들 수 있습니다. 자세히: /help"])
        try:
            sent = self.bot.send(text, [("자동으로 정하기", "q:auto"), ("오늘은 건너뛰기", "q:skip")])
        except TelegramError as e:  # 묻지 못했으면 오늘 물은 것으로 치지 않는다 (다음 시각에 다시)
            raise ApiError(502, "telegram_failed", f"텔레그램으로 묻지 못했다: {e}") from None
        st = self._load()
        st.update({"askedDate": today, "waiting": True, "category": category, "count": count,
                   "messageId": (sent or {}).get("message_id")})
        st.pop("want", None)
        self._save(st)

    def _change_plan(self, series_id: str) -> str:
        """[다른 주제로]: 승인 대기 계획을 취소하고 바로 주제·화 수를 묻는다 (2026-10-21 사용자)"""
        with self.db() as s:
            series = s.get(Series, series_id)
            if series is None:
                return f"시리즈가 없습니다: {series_id}"
            if series.status != "PROPOSED":  # 버튼을 남겨 둔다(ApiError)
                raise ApiError(409, "series_not_proposed", f"승인 대기 계획만 바꿀 수 있다. 지금: {series.status}")
            cancel_domain.cancel_series(s, series, self.clock(), WHO, "텔레그램 [다른 주제로]")
            title, category = series.title, series.category
            s.commit()
        with self._state_lock:
            self._send_question(category, DEFAULT_COUNT)
        return f"🔄 계획 취소: {title}. 새 주제를 물었습니다"

    def _handle_message(self, msg: dict[str, Any]) -> None:
        chat = str((msg.get("chat") or {}).get("id", ""))
        if chat != self.bot.chat_id or str((msg.get("from") or {}).get("id", "")) != self.bot.chat_id:
            return  # 다른 대화에는 답하지 않는다
        text = str(msg.get("text") or "").strip()
        cmd = re.split(r"\s", text, maxsplit=1)[0].split("@", 1)[0]  # '/series' 다음이 줄바꿈이어도
        if cmd == "/status":  # 현황 (n8n 0번 현황 폼과 같은 내용)
            self._safe_send(self.status_text(), None)
            return
        if cmd in ("/help", "/start"):
            self._safe_send(HELP, None)
            return
        if cmd == "/news":
            self._news_command(text.split(" ", 1)[1].strip() if " " in text else "")
            return
        if cmd == "/run":
            self._safe_send(self.production.run()["message"] if self.production else "생산 시작 기능이 꺼져 있습니다", None)
            return
        if cmd == "/top":
            self._top_command(re.split(r"\s", text, maxsplit=1)[1] if re.search(r"\s", text) else "")
            return
        with self._state_lock:
            st = self._load()
            if cmd == "/series":
                body = re.split(r"\s", text, maxsplit=1)[1] if re.search(r"\s", text) else ""
                if not body.strip():
                    self._safe_send(f"/series 주제, 화수 로 다음 시리즈 계획을 만듭니다. {EXAMPLE}", None)
                    return
            elif st.get("waiting") and not text.startswith("/"):
                body = text
            else:
                return  # 묻는 중이 아닐 때의 글은 답으로 받지 않는다
            try:
                req = parse_request(body)
            except ValueError as e:
                self._safe_send(f"⚠️ {e}. {EXAMPLE}", None)
                return
            if self._plan_waiting():
                self._safe_send("승인 대기 계획이 있어 새 계획을 만들지 않았습니다. 그 계획을 먼저 승인하거나 n8n 폼에서 처리해 주세요.", None)
                return
            self._want(st, req.theme, req.count, req.references, req.episodes)
        extra = (f" · 참고 자료 {len(req.references)}개" if req.references else "") + (" · 화 제목 직접" if req.episodes else "")
        self._safe_send(f"⏳ 계획을 만드는 중입니다: {req.theme}, {req.count}화{extra}", None)

    def _question_button(self, target: str) -> str:
        with self._state_lock:
            st = self._load()
            if not st.get("waiting"):
                return "이미 처리한 질문입니다"
            if target == "skip":
                st["waiting"] = False
                self._save(st)
                return "⏭ 오늘은 건너뜁니다. 내일 다시 묻습니다 (언제든 /series 주제, 화수)."
            if target == "auto":
                if self._plan_waiting():
                    return "승인 대기 계획이 있어 새 계획을 만들지 않았습니다"
                self._want(st, None, int(st.get("count") or DEFAULT_COUNT))
                return "🤖 주제를 자동으로 정합니다. 계획이 나오면 [계획 승인] 메시지를 보냅니다."
        return f"모르는 버튼: q:{target}"

    def _top_command(self, body: str) -> None:
        """/top 주제, 개수 (+참고 자료, +항목 이름): 목록형 쇼츠 작업을 만든다 (D42). 다음 정각 1번 워크플로가 만든다"""
        if not body.strip():
            self._safe_send(f"/top 주제, 개수 로 목록형 쇼츠를 만듭니다. {TOP_EXAMPLE}", None)
            return
        try:
            req = parse_request(body, default=TOP_DEFAULT, lo=TOP_MIN, hi=TOP_MAX, unit="항목")
        except ValueError as e:
            self._safe_send(f"⚠️ {e}. {TOP_EXAMPLE}", None)
            return
        try:
            with self.db() as s:
                job = jobs_domain.create_listicle_job(s, self.settings, self.clock(), topic=req.theme, count=req.count,
                                                      references=req.references, items=[i[:60] for i in req.episodes])
                s.commit()
                job_id = job.id
        except ApiError as e:
            self._safe_send(f"⚠️ {e.message}", None)
            return
        extra = (f" · 참고 자료 {len(req.references)}개" if req.references else "") + (" · 항목 직접" if req.episodes else "")
        self._safe_send(f"✅ 목록형 쇼츠 등록: {req.theme}, {req.count}개{extra} ({job_id})\n다음 정각 생산에서 먼저 만듭니다. 진행은 /status", None)

    def _news_command(self, arg: str) -> None:
        """/news: 새 글 모아 평가해 보내기, /news 더: 다음 후보, /news <GeekNews 주소>: 그 글을 평가해 보내기"""
        if self.news is None:
            self._safe_send("IT 뉴스 기능이 꺼져 있습니다", None)
            return
        if arg in ("더", "more"):
            if not self.news.more():
                self._safe_send("📰 더 보낼 후보가 없습니다. /news 로 새 글을 모읍니다.", None)
            return
        if arg:
            self._safe_send("⏳ 그 글을 평가하는 중입니다", None)
            work = lambda: self.news.add_link(arg)  # noqa: E731
        else:
            self._safe_send("⏳ GeekNews 새 글을 모으는 중입니다. 평가되는 대로 하나씩 보냅니다 (그동안 다른 버튼도 됩니다)", None)
            work = self.news.daily

        def run() -> None:
            try:
                work()
            except ApiError as e:
                self._safe_send(f"⚠️ {e.message}", None)
            except Exception:  # 따로 도는 일이라 실패를 알려야 한다
                log.exception("/news 실패")
                self._safe_send("⚠️ /news 를 끝내지 못했습니다. 잠시 뒤 다시 보내 주세요.", None)
        self.run_background(run)

    def plan_sent(self) -> dict[str, str]:
        return dict(self._load().get("planSent") or {})

    def question_state(self) -> dict[str, Any]:
        """다음 시리즈 주제 질문이 지금 어떤 상태인가 (현황용)"""
        st = self._load()
        want, today = st.get("want"), kst_date(self.clock())
        if want:
            label = f"계획 만드는 중: {want.get('theme') or '자동 주제'}, {want.get('count')}화"
            if want.get("toldBusy"):
                label += " (다른 작업이 끝나면 만듦)"
        elif st.get("waiting"):
            label = f"답을 기다리는 중 ({st.get('askedDate')} 물음). 텔레그램에 '주제, 화수'로 답하거나 버튼을 누르세요"
        elif self._plan_waiting():
            label = "승인 대기 계획이 있어 묻지 않음"
        elif st.get("askedDate") == today:
            label = "오늘은 물었음(건너뜀). 내일 다시 묻습니다"
        else:
            label = "남은 화가 10편보다 적어지면 n8n 3번이 묻습니다 (언제든 /series 주제, 화수)"
        return {"label": label, "askedDate": st.get("askedDate"), "waiting": bool(st.get("waiting")), "want": want}

    def status_text(self) -> str:
        return overview.collect(self.db, self.clock, telegram=self, asmr=self.asmr, news=self.news)["text"]

    def _want(self, st: dict[str, Any], theme: Optional[str], count: int, references: Optional[list[str]] = None,
              episodes: Optional[list[str]] = None) -> None:
        """만들 계획을 상태 파일에 적는다. 실제 생성은 make_wanted_plan (제작 중이면 끝난 뒤)"""
        st.update(waiting=False, want={"theme": theme, "count": count, "category": st.get("category") or "ai-it",
                                       "references": references or [], "episodes": episodes or []})
        self._save(st)

    def make_wanted_plan(self) -> None:
        """적어 둔 계획 요청을 만든다. 다른 작업이 실행 중이면 그대로 두고 다음 받기 때 다시 (전역 잠금, D4)"""
        want = self._load().get("want")
        if not want or self.runner is None:
            return
        try:
            if self.providers is None:
                raise ApiError(503, "llm_unavailable", "LLM 제공자 설정(providers.yaml)이 없다")
            llm = self.providers.llm("series_plan")
            refs, unread = self._read_references(want.get("references") or [])
            if unread:
                self._safe_send("⚠️ 참고 자료를 읽지 못해 빼고 만듭니다: " + ", ".join(unread), None)
            with self.runner.exclusive("시리즈 계획 생성"), self.db() as s:
                now = self.clock()
                series = generation.generate_series_plan(
                    s, self.settings, now, llm, key=generation.next_series_key(s, now), category=want["category"],
                    title=None, count=int(want["count"]), bible=None, theme=want.get("theme"),
                    references=refs or None, episode_titles=want.get("episodes") or None)
                s.commit()
                series_id = series.id
        except ApiError as e:
            if e.code == "busy":
                if not want.get("toldBusy"):
                    self._safe_send("다른 작업이 실행 중이라 끝나면 바로 계획을 만듭니다.", None)
                    self._edit_state(lambda st: st.get("want", {}).update(toldBusy=True))
                return
            self._fail_want(e.message)
            return
        except Exception as e:  # 계획 하나의 실패가 받기 루프를 멈추지 않게
            log.exception("시리즈 계획 생성 실패")
            self._fail_want(type(e).__name__)
            return
        self._clear_want()
        self.notify_plan(series_id)

    def _edit_state(self, fn: Callable[[dict[str, Any]], None]) -> None:
        with self._state_lock:
            st = self._load()
            fn(st)
            self._save(st)

    def _read_references(self, urls: list[str]) -> tuple[list[dict[str, str]], list[str]]:
        """참고 자료를 IT 뉴스 원문 읽기와 같은 방식(SSRF 검사, 본문만)으로 읽는다. ([{url, text}], [못 읽은 주소])"""
        read, unread = [], []
        for url in urls:
            text = self.news.fetch_article(url) if self.news is not None else None
            (read.append({"url": url, "text": text}) if text else unread.append(url))
        return read, unread

    def _clear_want(self) -> None:
        self._edit_state(lambda st: st.pop("want", None))

    def _fail_want(self, why: str) -> None:
        self._clear_want()
        self._safe_send(f"⚠️ 시리즈 계획을 만들지 못했습니다: {why}\n/series 주제, 화수 로 다시 요청할 수 있습니다.", None)

    # ---------- 검토 대기 다시 알림

    def remind_due(self) -> None:
        """검토 대기가 REMIND_SEC 넘게 남고, 지금 승인할 수 있는 차례인 영상을 다시 알린다 (오래된 것부터 MAX_REMIND 개)"""
        now = self.clock()
        with self.db() as s:
            due = []
            for job in s.scalars(select(Job).where(Job.status == "REVIEW").order_by(Job.updated_at, Job.id)):
                last = self._reminded.get(job.id) or job.updated_at
                if last is None or (now - last).total_seconds() < REMIND_SEC or not self._approvable(s, job):
                    continue
                due.append(job.id)
        for job_id in due[:MAX_REMIND]:
            self.notify_review(job_id, reminder=True)
            self._reminded[job_id] = now
        self._remind_plans(now)
        self._ask_stuck(now)
        self._ask_transient(now)
        if self.asmr is not None:
            self.asmr.remind_due()

    # ---------- 대본 검토에서 계속 떨어진 화 (2026-10-21)

    def _ask_stuck(self, now) -> None:
        """검토가 3번 연속 점수 미달인 화에 [개요 고쳐 다시][건너뛰기] 를 묻는다 (작업마다 하루 한 번)"""
        with self.db() as s:
            items = []
            for x in stuck.find_stuck(s):
                job = x["job"]
                series = s.get(Series, job.series_id)
                items.append((job.id, f"{series_order.label(s, series)} {job.episode_number}화 {job.topic}", x["errors"][-1]))
        asked = self._load().get("stuckAsked") or {}
        for job_id, head, last in items:
            if job_id in asked and (now - datetime.fromisoformat(asked[job_id])).total_seconds() < PLAN_REMIND_SEC:
                continue
            text = (f"✍️ 대본이 {stuck.STUCK_AFTER}번 연속 통과하지 못함: {head}\n마지막 이유: {last[:600]}\n"
                    "[개요 고쳐 다시]: 검토 의견으로 개요를 고쳐 대본부터 다시 만들고 승인을 요청합니다\n"
                    "[건너뛰기]: 이 화를 빼고 다음 화로 넘어갑니다")
            try:
                self.bot.send(text, [("개요 고쳐 다시", f"ro:{job_id}"), ("건너뛰기", f"rs:{job_id}")])
            except TelegramError as e:
                log.warning("텔레그램 보내기 실패: %s", e)
                continue
            sent = now.isoformat()
            self._edit_state(lambda st, j=job_id: st.setdefault("stuckAsked", {}).__setitem__(j, sent))

    def _ask_transient(self, now) -> None:
        """일시적 오류로 멈춘 작업에 [다시 시도] (시리즈 화면 [건너뛰기] 도) 를 묻는다 (작업마다 하루 한 번)"""
        with self.db() as s:
            items = []
            for x in stuck.find_transient(s):
                job = x["job"]
                if job.series_id:
                    head = f"{series_order.label(s, s.get(Series, job.series_id))} {job.episode_number}화 {job.topic}"
                else:
                    head = job.topic
                items.append((job.id, head, x["step"], x["error"], bool(job.series_id)))
        asked = self._load().get("stuckAsked") or {}
        for job_id, head, step, error, is_series in items:
            if job_id in asked and (now - datetime.fromisoformat(asked[job_id])).total_seconds() < PLAN_REMIND_SEC:
                continue
            text = (f"⚠️ 일시적 오류로 멈춤: {head}\n{step} 단계, 3번 실패: {error[:400]}\n"
                    "[다시 시도]: 그 단계부터 다음 정각에 이어서 만듭니다 (Codex·LLM 서버가 살아났는지 /status 로 먼저 확인)")
            buttons = [("다시 시도", f"rt:{job_id}")] + ([("건너뛰기", f"rs:{job_id}")] if is_series else [])
            try:
                self.bot.send(text, buttons)
            except TelegramError as e:
                log.warning("텔레그램 보내기 실패: %s", e)
                continue
            sent = now.isoformat()
            self._edit_state(lambda st, j=job_id: st.setdefault("stuckAsked", {}).__setitem__(j, sent))

    def _retry_failed(self, job_id: str) -> str:
        if self.runner is None:
            raise ApiError(503, "runner_unavailable", "실행기가 없다")
        with self.db() as s:
            x = next((i for i in stuck.find_transient(s) if i["job"].id == job_id), None)
            if x is None:
                raise ApiError(409, "not_transient_failed", "일시적 오류로 멈춘 작업이 아닙니다(이미 처리됨)")
            step, head = x["step"], x["job"].topic
        self.runner.reset(job_id, step)
        self._edit_state(lambda st: (st.get("stuckAsked") or {}).pop(job_id, None))
        return f"🔁 다시 시도: {head} ({step} 단계부터, 다음 생산 시각에)"

    def _fix_outline(self, job_id: str) -> str:
        if self.runner is None or self.providers is None:
            raise ApiError(503, "llm_unavailable", "LLM 설정이 없어 개요를 고칠 수 없다")
        llm = self.providers.llm("outline_fix")  # 따로 정하지 않으면 대본 단계 제공자 (Codex)
        with self.runner.exclusive("개요 고치기"), self.db() as s:  # 제작 중이면 busy → 버튼을 남겨 다시 누르게
            new = stuck.revise_outline(s, self.clock(), llm, job_id)
            job = s.get(Job, job_id)
            head = f"{job.episode_number}화 {job.topic}"
            s.commit()
        self.runner.reset(job_id, "topic")  # 주제 단계가 고친 개요를 다시 읽는다 → 생산 워크플로가 대본부터 다시
        self._edit_state(lambda st: (st.get("stuckAsked") or {}).pop(job_id, None))
        return f"✍️ {head} 개요를 고쳤습니다. 다음 생산 시각에 대본부터 다시 만들고 승인을 요청합니다.\n새 개요: {new[:800]}"

    def _skip_episode(self, job_id: str) -> str:
        with self.db() as s:
            ep = stuck.skip_episode(s, self.clock(), job_id, WHO)
            head = f"{ep.number}화 {ep.title}"
            s.commit()
        self._edit_state(lambda st: (st.get("stuckAsked") or {}).pop(job_id, None))
        return f"⏭ {head} 건너뜀. 다음 생산 시각에 다음 화를 만듭니다"

    def _remind_plans(self, now) -> None:
        """승인 대기 계획을 하루에 한 번 다시 보낸다. 보낸 기록이 없으면(기록 전에 만든 계획) 바로 (2026-10-20 실제: 놓친 계획이 그대로 멈춤)"""
        with self.db() as s:
            ids = list(s.scalars(select(Series.id).where(Series.status == "PROPOSED").order_by(Series.created_at)))
        sent = self.plan_sent()
        for sid in ids:
            last = sent.get(sid)
            if last is None or (now - datetime.fromisoformat(last)).total_seconds() >= PLAN_REMIND_SEC:
                self.notify_plan(sid, reminder=last is not None)

    @staticmethod
    def _approvable(s, job: Job) -> bool:
        """지금 승인 버튼을 누르면 받아들여지는가 (화 순서 D24, 시리즈 순서 D33 과 같은 규칙)"""
        if not job.series_id:
            return True
        ep = s.scalar(select(Episode).where(Episode.series_id == job.series_id, Episode.number == job.episode_number))
        if ep is None:
            return True
        if ep.number > 1:
            prev = s.scalar(select(Episode).where(Episode.series_id == job.series_id, Episode.number == ep.number - 1))
            return prev is not None and prev.status in EP_DONE
        series = s.get(Series, job.series_id)
        return series is None or series_order.approval_blocker(s, series) is None

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
                    self.remind_due()
                except Exception as e:
                    log.warning("텔레그램 받기 실패, 10초 뒤 다시: %s", e)
                    self._stop.wait(10)
        self._thread = threading.Thread(target=loop, name="telegram", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
