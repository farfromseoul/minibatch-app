"""IT 뉴스 후보 (아키텍처 D40, IT뉴스 기획서 2026-10-25).

- collect: GeekNews RSS 에서 최근 48시간 새 글을 넣고, 글 페이지에서 원문 링크·추천 수를 읽고(후보마다 한 번, 요청 사이 쉼),
  추천 수가 높은 글부터 원문을 읽어 LLM 으로 평가한다(점수·우리 말 3줄 요약·품질·저작권 판단). 원문을 못 읽으면 '원문 확인 불가'
- send: 평가되는 대로 바로 보낸다(후보마다 [이걸로], 한 번에 news_candidates 개). 끊긴 실행이 평가만 하고 못 보낸 후보는
  다음 실행이 먼저 보낸다 (2026-10-26: 다 평가한 뒤 한꺼번에 보내다가 재시작으로 하나도 못 보냈다)
- pick: [이걸로] → it-news 단독 작업. 하루 news_daily_max(기본 3)까지
- fetch_article: 주제 단계가 원문을 읽을 때 같은 SSRF 검사로
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta
from typing import Any, Callable, Optional
from urllib.parse import urljoin

import httpx
from sqlalchemy import func, select

from app.core.errors import ApiError
from app.core.timeutil import kst_day_start_utc
from app.db.models import NewsItem
from app.domain import jobs as jobs_domain
from app.domain.generation import _ask
from app.llm.prompting import render_messages
from app.notify.telegram import TelegramError

from . import article, geeknews

log = logging.getLogger("job-api.news")

WINDOW = timedelta(hours=48)  # 이보다 오래된 글은 후보로 넣지 않는다 (시의성)
MAX_TOPIC_PAGES = 15          # 한 번에 읽는 GeekNews 글 페이지 수 (약관: 과도한 부하 금지)
MAX_EVAL = 8                  # 한 번에 LLM 으로 평가하는 수
CATEGORY = "it-news"
RISK_KO = {"low": "낮음", "medium": "보통", "high": "높음"}
EVAL_SCHEMA = {"type": "object", "properties": {
    "summary": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
    "score": {"type": "integer", "minimum": 1, "maximum": 10},
    "quality": {"type": "string"},
    "copyright_risk": {"type": "string", "enum": ["low", "medium", "high"]},
    "copyright": {"type": "string"}},
    "required": ["summary", "score", "quality", "copyright_risk", "copyright"], "additionalProperties": False}


class NewsService:
    def __init__(self, settings, *, db: Callable, clock: Callable, providers=None, bot=None,
                 http: Optional[httpx.Client] = None, resolve: Optional[Callable] = None):
        self.settings, self.db, self.clock, self.providers, self.bot = settings, db, clock, providers, bot
        self.http = http or httpx.Client(timeout=20)
        self.resolve = resolve or article.resolve_host
        self.pause_sec = 1.0  # GeekNews 요청 사이 쉼
        self._lock = threading.Lock()

    # ---------- 읽기

    def _get(self, url: str) -> Optional[str]:
        """GeekNews RSS·글 페이지. 리디렉션은 따라가되 한 단계씩 원문 읽기와 같은 주소 검사를 한다
        (2026-10-30: RSS 가 FeedBurner 로 302 리디렉션돼 '읽지 못했다'로 끝났다)"""
        for _ in range(article.MAX_REDIRECTS + 1):
            if not article.safe_url(url, self.resolve):
                log.warning("GeekNews 주소 검사에서 거절: %s", url)
                return None
            try:
                res = self.http.get(url, headers={"User-Agent": article.UA}, timeout=20, follow_redirects=False)
            except httpx.HTTPError as e:
                log.warning("GeekNews 읽기 실패 %s: %s", url, type(e).__name__)
                return None
            if res.status_code in (301, 302, 303, 307, 308) and res.headers.get("location"):
                url = urljoin(url, res.headers["location"])
                continue
            if res.status_code != 200:
                log.warning("GeekNews 읽기 실패 %s: %s", url, res.status_code)
                return None
            return res.text
        return None

    def fetch_article(self, url: Optional[str]) -> Optional[str]:
        return article.fetch_text(url, self.http, self.resolve) if url else None

    # ---------- 모으기·평가

    def collect(self, on_ready: Optional[Callable[[str], None]] = None) -> int:
        """새 글을 넣고 평가한다. 새로 평가한 수. on_ready: 원문을 읽어 평가한 후보마다 바로 부른다(보내기)"""
        now = self.clock()
        feed = self._get(self.settings.extra.get("news_feed_url", geeknews.FEED_URL))
        if feed is None:
            raise ApiError(502, "news_feed_failed", "GeekNews RSS 를 읽지 못했다")
        with self.db() as s:
            for e in geeknews.parse_feed(feed):
                if e["published"] is not None and now - e["published"] > WINDOW:
                    continue
                if s.get(NewsItem, f"gn-{e['id']}") is None:
                    s.add(NewsItem(id=f"gn-{e['id']}", gn_url=e["url"], title=e["title"][:300], gn_summary=e["summary"][:4000],
                                   published_at=e["published"], status="NEW", created_at=now, updated_at=now))
            s.commit()
        return self._evaluate_new(on_ready)

    def _read_topic(self, item_id: str) -> None:
        with self.db() as s:
            item = s.get(NewsItem, item_id)
            url, tid = item.gn_url, item_id.removeprefix("gn-")
        page = self._get(url)
        time.sleep(self.pause_sec)
        info = geeknews.parse_topic(page, tid) if page else {"source": None, "points": None}
        with self.db() as s:
            item = s.get(NewsItem, item_id)
            item.source_url, item.points, item.updated_at = info["source"], info["points"], self.clock()
            if not info["source"]:
                item.readable, item.status = False, "EVALUATED"
            s.commit()

    def _evaluate_new(self, on_ready: Optional[Callable[[str], None]] = None) -> int:
        with self.db() as s:
            new = list(s.scalars(select(NewsItem.id).where(NewsItem.status == "NEW", NewsItem.source_url.is_(None))
                                 .order_by(NewsItem.published_at.desc(), NewsItem.id.desc()).limit(MAX_TOPIC_PAGES)))
        for item_id in new:
            self._read_topic(item_id)
        with self.db() as s:
            todo = list(s.scalars(select(NewsItem.id).where(NewsItem.status == "NEW", NewsItem.source_url.is_not(None))
                                  .order_by(NewsItem.points.desc(), NewsItem.id.desc()).limit(MAX_EVAL)))
        done = 0
        for item_id in todo:
            try:
                self.evaluate(item_id)
            except Exception as e:  # 한 글의 평가 실패가 나머지를 막지 않게. NEW 로 남아 다음 실행에서 다시
                log.warning("후보 평가 실패 %s: %s", item_id, getattr(e, "message", type(e).__name__))
                continue
            done += 1
            if on_ready is not None:
                on_ready(item_id)
        return done

    def evaluate(self, item_id: str) -> None:
        with self.db() as s:
            item = s.get(NewsItem, item_id)
            title, points, gn_summary, source_url = item.title, item.points, item.gn_summary, item.source_url
        text = self.fetch_article(source_url)
        result: dict[str, Any] = {"readable": text is not None}
        if text is not None:
            if self.providers is None:
                raise ApiError(503, "llm_unavailable", "LLM 설정이 없어 후보를 평가할 수 없다")
            messages, _ = render_messages("news_eval", title=title, points=points if points is not None else "?",
                                          gn_summary=gn_summary or "(없음)", source=text[:3000])
            data = _ask(self.providers.llm("news_eval"), messages, EVAL_SCHEMA, "news_eval",
                        lambda d: [] if isinstance(d, dict) and len(d.get("summary") or []) == 3 else ["summary 는 정확히 3줄"])
            result.update(score=int(data["score"]), summary=[str(x) for x in data["summary"]], quality=str(data["quality"]),
                          copyright_risk=str(data["copyright_risk"]), copyright=str(data["copyright"]))
        with self.db() as s:
            item = s.get(NewsItem, item_id)
            for k, v in result.items():
                setattr(item, k, v)
            item.status = "EVALUATED" if item.status in ("NEW", "EVALUATED") else item.status
            item.updated_at = self.clock()
            s.commit()

    # ---------- 보내기

    def daily(self) -> dict[str, Any]:
        """매일 07:00 (n8n 7번) 과 /news: 못 보낸 후보 먼저 → 새 글을 모아 평가되는 대로 보낸다 → 끝에 요약"""
        with self._lock:
            sent = self._send_ready(self.settings.news_candidates)

            def ready(item_id: str) -> None:
                if sent[0] < self.settings.news_candidates:
                    sent[0] += self._send_ready(1, only=item_id, start=sent[0] + 1)[0]

            evaluated = self.collect(on_ready=ready)
            self._summary(sent[0], more_hint=True)
        return {"evaluated": evaluated, "sent": sent[0]}

    def more(self) -> int:
        with self._lock:
            n = self._send_ready(self.settings.news_candidates)[0]
            if n:
                self._summary(n, more_hint=True)
            return n

    def _picked_today(self, s) -> int:
        return s.scalar(select(func.count()).select_from(NewsItem)
                        .where(NewsItem.picked_at >= kst_day_start_utc(self.clock()))) or 0

    def _send_ready(self, limit: int, only: Optional[str] = None, start: int = 1) -> list[int]:
        """평가했지만 안 보낸 후보를 점수 순으로 limit 개 보낸다. [보낸 수] (daily 의 클로저가 고칠 수 있게 리스트)"""
        now = self.clock()
        with self.db() as s:
            q = (select(NewsItem).where(NewsItem.status == "EVALUATED", NewsItem.readable.is_(True),
                                        NewsItem.created_at >= now - WINDOW)
                 .order_by(NewsItem.score.desc(), NewsItem.points.desc(), NewsItem.id))
            if only:
                q = q.where(NewsItem.id == only)
            items = list(s.scalars(q.limit(limit)))
            for rank, item in enumerate(items, start=start):
                self._send_item(item, rank)
                item.status, item.sent_at = "SENT", now
            s.commit()
            return [len(items)]

    def _summary(self, sent: int, more_hint: bool) -> None:
        """보낸 수·오늘 고른 수·원문 확인 불가 글. 원문을 못 읽은 글은 여기서 '보냄'으로 정리한다"""
        now = self.clock()
        with self.db() as s:
            bad = list(s.scalars(select(NewsItem).where(NewsItem.status == "EVALUATED", NewsItem.readable.is_(False))))
            picked = self._picked_today(s)
            if not sent:
                self._send("📰 새 후보가 없습니다. 새 글이 올라오면 /news 로 다시 모읍니다.")
            else:
                lines = [f"📰 후보 {sent}개를 보냈습니다 · 오늘 고른 {picked}/{self.settings.news_daily_max}",
                         "원문을 읽어 보고 [이걸로 만들기] 를 누르세요." + (" 더 보기: /news 더" if more_hint else "")]
                if bad:
                    lines.append("원문 확인 불가(고를 수 없음): " + ", ".join(i.title[:30] for i in bad[:5]))
                self._send("\n".join(lines))
            for i in bad:
                i.status, i.sent_at = "SENT", now
            s.commit()

    def _send_item(self, item: NewsItem, rank: int) -> None:
        points = f" · GeekNews {item.points}P" if item.points is not None else ""
        lines = [f"📰 {rank}. {item.title}{points}",
                 f"점수 {item.score}/10 · 품질: {item.quality}",
                 f"저작권 위험 {RISK_KO.get(item.copyright_risk or '', item.copyright_risk)}: {item.copyright}",
                 *[f"- {x}" for x in (item.summary or [])],
                 f"원문: {item.source_url}", f"GeekNews: {item.gn_url}"]
        self._send("\n".join(lines), [("이걸로 만들기", f"n:{item.id}")])

    def _send(self, text: str, buttons=None) -> None:
        if self.bot is None:
            return
        try:
            self.bot.send(text, buttons)
        except TelegramError as e:
            log.warning("텔레그램 보내기 실패: %s", e)

    def add_link(self, url: str) -> None:
        """/news <GeekNews 글 주소>: 그 글을 평가해 보낸다 (이미 본 글이어도)"""
        tid = geeknews.topic_id(url)
        if not tid:
            raise ApiError(422, "not_geeknews", "GeekNews 글 주소(news.hada.io/topic?id=…)를 주세요")
        now = self.clock()
        with self._lock:
            with self.db() as s:
                item = s.get(NewsItem, f"gn-{tid}")
                if item is None:
                    item = NewsItem(id=f"gn-{tid}", gn_url=geeknews.topic_url(tid), title=f"GeekNews {tid}", gn_summary="",
                                    status="NEW", created_at=now, updated_at=now)
                    s.add(item)
                elif item.status == "PICKED":
                    raise ApiError(409, "news_picked", "이미 고른 글이다")
                item.status, item.created_at = "NEW", now
                s.commit()
            page = self._get(geeknews.topic_url(tid))
            if page:
                with self.db() as s:
                    item = s.get(NewsItem, f"gn-{tid}")
                    h1 = geeknews.TITLE_LINK.search(page)
                    title = geeknews.text_of(page[h1.end(): page.find("</a>", h1.end())]) if h1 else ""
                    if title:
                        item.title = title[:300]
                    s.commit()
            self._read_topic(f"gn-{tid}")
            with self.db() as s:
                needs_eval = s.get(NewsItem, f"gn-{tid}").status == "NEW"
            if needs_eval:
                self.evaluate(f"gn-{tid}")
            n = self._send_ready(1, only=f"gn-{tid}")[0]
            if not n:
                self._send("📰 그 글은 원문을 읽을 수 없어 후보로 만들 수 없습니다.")

    # ---------- 고르기

    def pick(self, item_id: str) -> str:
        now = self.clock()
        with self._lock, self.db() as s:
            item = s.get(NewsItem, item_id)
            if item is None:
                raise ApiError(404, "news_not_found", f"후보가 없다: {item_id}")
            if item.status == "PICKED":
                raise ApiError(409, "news_picked", "이미 고른 글입니다")
            if not item.readable:
                raise ApiError(409, "news_unreadable", "원문을 읽을 수 없어 만들 수 없습니다")
            picked = self._picked_today(s)
            if picked >= self.settings.news_daily_max:
                raise ApiError(409, "news_daily_max", f"오늘은 이미 {picked}편을 골랐습니다(하루 최대 {self.settings.news_daily_max}편)")
            job = jobs_domain.create_news_job(s, self.settings, now, title=item.title, news={
                "id": item.id, "title": item.title, "gnUrl": item.gn_url, "sourceUrl": item.source_url,
                "gnSummary": item.gn_summary, "points": item.points})
            item.status, item.picked_at, item.job_id, item.updated_at = "PICKED", now, job.id, now
            s.commit()
            return f"✅ 고름: {item.title}\n다음 생산 시각에 만듭니다 (오늘 {picked + 1}/{self.settings.news_daily_max})"

    # ---------- 현황

    def counts(self) -> dict[str, Any]:
        now = self.clock()
        with self.db() as s:
            sent = s.scalar(select(func.count()).select_from(NewsItem).where(NewsItem.sent_at >= kst_day_start_utc(now))) or 0
            return {"pickedToday": self._picked_today(s), "max": self.settings.news_daily_max, "sentToday": sent}
