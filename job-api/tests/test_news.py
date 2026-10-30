"""IT 뉴스 (아키텍처 D40, IT뉴스 기획서 2026-10-25).

매일 07:00 GeekNews RSS 에서 후보를 모아 평가(점수·품질·저작권)하고 텔레그램으로 보낸다 → [이걸로] → it-news 단독 작업
→ 주제 단계가 원문을 읽어 사실 목록 → 대본·검토가 사실 목록을 쓴다 → 설명란에 원문·GeekNews 출처.
GeekNews·원문 사이트에는 접속하지 않는다(가짜 HTTP). LLM 도 가짜.
"""
import json
import pathlib
import shutil

import httpx

from app.news import article
from app.news.service import NewsService
from app.pipeline.steps.publishing import _description
from tests.fakes import FakeLlm, FakeRegistry
from tests.test_telegram import TelegramCase

REAL = pathlib.Path(__file__).resolve().parents[1] / "content" / "categories"

FEED = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom'>
<title>GeekNews</title>
{entries}
</feed>"""
ENTRY = """<entry><title><![CDATA[{title}]]></title>
<link rel='alternate' type='text/html' href='https://news.hada.io/topic?id={id}' />
<id>https://news.hada.io/topic?id={id}</id>
<published>{published}</published><updated>{published}</updated>
<content type='html'><![CDATA[<ul><li>{summary}</li></ul>]]></content></entry>"""
TOPIC = """<html><body><div class='topictitle link'><a href='{src}' class='bold ud topic-title-link'><h1>{title}</h1></a></div>
<div class=topicinfo><span id='tp{id}'>{points}</span>P by neo</div></body></html>"""
ARTICLE = """<html><head><title>x</title><script>var a=1;</script></head><body><nav>메뉴</nav>
<article><h1>{title}</h1><p>{body}</p><p>둘째 문단입니다. 버전 2.0 은 2026년 10월에 나왔다.</p></article><footer>저작권</footer></body></html>"""


def evaluation(score, risk="low"):
    return {"summary": ["무엇이 나왔나", "왜 중요한가", "개발자에게 바뀌는 것"], "score": score,
            "quality": "공식 발표, 근거 있음", "copyright_risk": risk, "copyright": "사실만 쓰면 문제 적음"}


FACTS = {"facts": ["Corgi 는 여러 코딩 에이전트를 한 화면에서 관리하는 터미널 도구다", "버전 2.0 은 2026년 10월에 나왔다",
                   "Claude Code 와 Codex 를 지원한다"],
         "angle": "여러 AI 코딩 에이전트를 동시에 쓰는 개발자에게 유용하다", "source_title": "Corgi"}


class FakeWeb:
    """GeekNews RSS·글 페이지·원문을 흉내 낸다. 주소 → (상태, 본문)"""

    def __init__(self):
        self.pages = {}
        self.requests = []

    def __call__(self, request):
        url = str(request.url)
        self.requests.append(url)
        status, body, ctype = self.pages.get(url, (404, "not found", "text/plain"))
        return httpx.Response(status, text=body, headers={"content-type": ctype})

    def add_topic(self, tid, title, src, points, published="2026-10-16T08:00:00+09:00"):
        self.pages[f"https://news.hada.io/topic?id={tid}"] = (200, TOPIC.format(src=src, title=title, id=tid, points=points), "text/html")
        return ENTRY.format(id=tid, title=title, summary=f"{title} 요약", published=published)

    def set_feed(self, entries):
        self.pages["https://news.hada.io/rss/news"] = (200, FEED.format(entries="".join(entries)), "application/atom+xml")

    def add_article(self, url, title, body="원문 첫 문단입니다."):
        self.pages[url] = (200, ARTICLE.format(title=title, body=body), "text/html; charset=utf-8")


def public_resolver(host):
    return ["10.1.2.3"] if host.endswith(".internal") else ["93.184.216.34"]


class NewsCase(TelegramCase):
    def setUp(self):
        self.llm = FakeLlm()
        self.web = FakeWeb()
        super().setUp()
        for f in ("ai-it.yaml", "it-news.yaml"):
            shutil.copy(REAL / f, self.settings.content_dir / "categories" / f)
        http = httpx.Client(transport=httpx.MockTransport(self.web))
        self.app.state.news.http = http
        self.app.state.news.resolve = public_resolver
        self.app.state.news.pause_sec = 0
        self.app.state.telegram_poller.run_background = lambda fn: fn()  # 테스트는 /news 를 바로 끝까지 돌린다

    def make_providers(self):
        return FakeRegistry(self.llm)

    def three(self):
        entries = [self.web.add_topic(101, "Corgi, 에이전트 멀티플렉서", "https://corgi.example/", 12),
                   self.web.add_topic(102, "PHP 재단 자금 부족", "https://php.example/news", 30),
                   self.web.add_topic(103, "사내 문서", "http://wiki.internal/secret", 5)]
        self.web.set_feed(entries)
        self.web.add_article("https://corgi.example/", "Corgi")
        self.web.add_article("https://php.example/news", "PHP")

    def daily(self):
        res = self.post("/news/daily")
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    def candidates(self):
        return [m for m in self.tg.sent("sendMessage") if m["text"].startswith("📰 ") and "reply_markup" in m]


class DailyTest(NewsCase):
    def test_candidates_are_scored_and_sent_best_first_with_links(self):
        self.three()
        self.llm.responses = [evaluation(9), evaluation(6)]  # 원문을 읽을 수 있는 두 글만 평가 (높은 추천 수부터)

        self.daily()

        msgs = self.candidates()
        self.assertEqual([m["reply_markup"]["inline_keyboard"][0][0]["callback_data"] for m in msgs], ["n:gn-102", "n:gn-101"])
        top = msgs[0]["text"]
        for want in ("PHP 재단 자금 부족", "https://php.example/news", "https://news.hada.io/topic?id=102", "9/10",
                     "30P", "저작권", "왜 중요한가"):
            self.assertIn(want, top)

    def test_private_address_is_never_fetched_and_marked(self):
        self.three()
        self.llm.responses = [evaluation(9), evaluation(6)]

        self.daily()

        self.assertNotIn("http://wiki.internal/secret", self.web.requests)
        texts = " ".join(m["text"] for m in self.tg.sent("sendMessage"))
        self.assertIn("원문 확인 불가", texts)

    def test_same_article_is_not_sent_again(self):
        self.three()
        self.llm.responses = [evaluation(9), evaluation(6)]
        self.daily()
        sent = len(self.candidates())

        self.daily()

        self.assertEqual(len(self.candidates()), sent)
        self.assertIn("새 후보가 없습니다", self.tg.sent("sendMessage")[-1]["text"])

    def test_rss_is_read_once_and_topic_pages_are_few(self):
        self.three()
        self.llm.responses = [evaluation(9), evaluation(6)]

        self.daily()

        self.assertEqual(self.web.requests.count("https://news.hada.io/rss/news"), 1)
        self.assertLessEqual(len([u for u in self.web.requests if "topic?id=" in u]), 15)


class PickTest(NewsCase):
    def picked_job(self):
        self.three()
        self.llm.responses = [evaluation(9), evaluation(6)]
        self.daily()
        self.tg.press("n:gn-102")
        self.poll()
        return self.get("/jobs?status=PENDING").json()["items"]

    def test_pick_makes_standalone_it_news_job(self):
        (job,) = self.picked_job()

        self.assertEqual((job["category"], job["seriesId"], job["topic"]), ("it-news", None, "PHP 재단 자금 부족"))
        self.assertIn("오늘 1/3", self.tg.sent("editMessageText")[-1]["text"])

    def test_fourth_pick_in_a_day_is_refused_and_button_stays(self):
        self.picked_job()
        for i, tid in enumerate((201, 202, 203)):
            entries = [self.web.add_topic(tid, f"글 {tid}", f"https://n{tid}.example/", 10)]
            self.web.set_feed(entries)
            self.web.add_article(f"https://n{tid}.example/", f"글 {tid}")
            self.llm.responses = [evaluation(8)]
            self.daily()
        self.tg.press("n:gn-201")
        self.tg.press("n:gn-202")
        self.poll()
        edits = len(self.tg.sent("editMessageText"))
        self.tg.press("n:gn-203")

        self.poll()

        self.assertIn("3편", self.tg.sent("answerCallbackQuery")[-1]["text"])
        self.assertEqual(len(self.tg.sent("editMessageText")), edits)

    def test_news_job_is_made_before_series_jobs(self):
        from tests.test_telegram import SERIES
        self.post("/series", SERIES)
        ep = self.post("/jobs", {"seriesId": "ai-office"}).json()["id"]
        (news,) = [j for j in self.picked_job() if j["category"] == "it-news"]

        self.assertEqual(self.get("/jobs/next").json()["jobId"], news["id"])
        self.assertNotEqual(news["id"], ep)


class ProductionTest(NewsCase):
    pipeline = ["topic", "script", "review"]

    def make_steps(self):
        return {}  # 진짜 주제·대본·검토 단계

    def news_job(self):
        self.three()
        self.llm.responses = [evaluation(9), evaluation(6)]
        self.daily()
        self.tg.press("n:gn-101")
        self.poll()
        return self.get("/jobs?status=PENDING").json()["items"][0]["id"]

    def test_topic_step_reads_source_and_writes_facts(self):
        job_id = self.news_job()
        self.llm.responses = [FACTS]

        self.assertEqual(self.run_step(job_id, "topic").status_code, 202)

        job = json.loads((self.job_dir(job_id) / "job.json").read_text())
        self.assertEqual(job["news"]["sourceUrl"], "https://corgi.example/")
        self.assertEqual(job["news"]["facts"], FACTS["facts"])
        self.assertIn("원문 첫 문단", self.llm.last_user_text())
        self.assertNotIn("메뉴", self.llm.last_user_text())  # 본문만 (nav·script 빼고)

    def test_script_uses_facts_and_rejects_copied_source_sentence(self):
        from tests.fakes import script_of
        job_id = self.news_job()
        copied = script_of(38, 8)
        copied["body"][0] = "버전 2.0 은 2026년 10월에 나왔다."  # 원문 문장 그대로
        self.llm.responses = [FACTS, copied, copied, copied]
        self.run_step(job_id, "topic")

        self.run_step(job_id, "script")

        prompt = [r for r in self.llm.requests if r["schema_name"] == "script"][0]["messages"][-1]["content"]
        self.assertIn("Corgi 는 여러 코딩 에이전트를", prompt)  # 사실 목록
        st = self.get(f"/jobs/{job_id}/steps/script").json()
        self.assertEqual(st["kind"], "deterministic")
        self.assertIn("원문", st["error"])

    def test_review_checks_against_facts(self):
        from tests.fakes import GOOD_SCORES, script_of
        job_id = self.news_job()
        self.llm.responses = [FACTS, script_of(38, 8), {"issues": [], "scores": GOOD_SCORES, "verdict": "pass"}]
        for step in ("topic", "script", "review"):
            self.run_step(job_id, step)

        self.assertIn("버전 2.0 은 2026년 10월에 나왔다", self.llm.last_user_text())


class DescriptionTest(NewsCase):
    def test_description_has_source_links(self):
        news = {"sourceUrl": "https://corgi.example/", "gnUrl": "https://news.hada.io/topic?id=101", "sourceTitle": "Corgi"}

        text = _description({"hook": "후킹", "summary": "요약", "hashtags": ["AI"]}, None, None, news)

        self.assertIn("원문: Corgi https://corgi.example/", text)
        self.assertIn("GeekNews 소개: https://news.hada.io/topic?id=101", text)


class CommandTest(NewsCase):
    def test_help_lists_all_commands(self):
        self.tg.say("/help")

        self.poll()

        text = self.tg.sent("sendMessage")[-1]["text"]
        for cmd in ("/status", "/series", "/news", "/news 더", "/help", "계획 승인", "개요 고쳐 다시", "업로드 승인"):
            self.assertIn(cmd, text)

    def test_news_command_collects_and_sends(self):
        self.three()
        self.llm.responses = [evaluation(9), evaluation(6)]
        self.tg.say("/news")

        self.poll()

        self.assertEqual(len(self.candidates()), 2)

    def test_news_more_sends_next_five(self):
        entries = []
        for tid in range(301, 309):
            entries.append(self.web.add_topic(tid, f"글 {tid}", f"https://n{tid}.example/", 100 - tid % 100))
            self.web.add_article(f"https://n{tid}.example/", f"글 {tid}")
        self.web.set_feed(entries)
        self.llm.responses = [evaluation(9 - i % 5) for i in range(8)]
        self.daily()
        first = len(self.candidates())
        self.tg.say("/news 더")

        self.poll()

        self.assertEqual((first, len(self.candidates()) - first), (5, 3))

    def test_news_with_geeknews_link_evaluates_that_topic(self):
        self.web.set_feed([])
        self.web.add_topic(401, "직접 고른 글", "https://mine.example/", 3)
        self.web.add_article("https://mine.example/", "직접")
        self.llm.responses = [evaluation(7)]
        self.tg.say("/news https://news.hada.io/topic?id=401")

        self.poll()

        (msg,) = self.candidates()
        self.assertIn("직접 고른 글", msg["text"])


class ArticleTest(NewsCase):
    def test_redirect_to_private_address_is_refused(self):
        self.web.pages["https://hop.example/"] = (302, "", "text/html")
        svc: NewsService = self.app.state.news

        def transport(request):
            if str(request.url) == "https://hop.example/":
                return httpx.Response(302, headers={"location": "http://db.internal/admin"})
            return httpx.Response(200, text="비밀")
        svc.http = httpx.Client(transport=httpx.MockTransport(transport))

        self.assertIsNone(article.fetch_text("https://hop.example/", svc.http, svc.resolve))

    def test_non_http_scheme_is_refused(self):
        svc: NewsService = self.app.state.news
        self.assertIsNone(article.fetch_text("file:///etc/passwd", svc.http, svc.resolve))


class SendAsEvaluatedTest(NewsCase):
    """평가되는 대로 바로 보낸다 (2026-10-26 실제: 평가를 다 마친 뒤 한꺼번에 보내는 구조라, 느린 평가 중에
    배포로 job-api 가 다시 시작되자 후보가 하나도 가지 않았다)"""

    def test_failed_evaluation_does_not_lose_already_sent_candidate(self):
        from tests.fakes import transient
        self.three()
        self.llm.responses = [evaluation(9), transient()]  # 두 번째 평가에서 LLM 일시 오류

        self.daily()

        self.assertEqual([m["reply_markup"]["inline_keyboard"][0][0]["callback_data"] for m in self.candidates()], ["n:gn-102"])
        self.assertEqual(self.get("/news/items?status=NEW").json()["items"][0]["id"], "gn-101")  # 다음 실행에서 다시 평가

    def test_evaluated_but_unsent_from_interrupted_run_is_sent_first(self):
        self.three()
        self.llm.responses = [evaluation(9), evaluation(6)]
        self.app.state.news.collect()  # 평가까지 하고 보내기 전에 끊겼다고 친다
        self.web.set_feed([])

        self.daily()

        self.assertEqual(len(self.candidates()), 2)


class BackgroundNewsTest(NewsCase):
    def test_news_command_runs_in_background_and_buttons_still_work(self):
        started = []
        self.app.state.telegram_poller.run_background = started.append  # 아직 돌리지 않는다
        job_id = self.new_job()
        self.run_until(job_id, "review")
        self.tg.say("/news")
        self.tg.press(f"a:{job_id}")

        self.poll()

        self.assertEqual(len(started), 1)  # 평가는 따로 맡겼고
        self.assertEqual(self.get(f"/jobs/{job_id}").json()["status"], "APPROVED")  # 그동안 버튼은 처리됐다
        self.assertIn("모으는 중", " ".join(m["text"] for m in self.tg.sent("sendMessage")))


class FeedRedirectTest(NewsCase):
    """2026-10-30 실제: GeekNews 가 RSS 를 FeedBurner 로 옮겨(302) '/news' 가 'RSS 를 읽지 못했다' 로 끝났다"""

    def test_feed_redirect_is_followed(self):
        self.three()
        feed = self.web.pages.pop("https://news.hada.io/rss/news")
        self.web.pages["https://feeds.feedburner.com/geeknews-feed"] = feed

        def transport(request):
            if str(request.url) == "https://news.hada.io/rss/news":
                return httpx.Response(302, headers={"location": "https://feeds.feedburner.com/geeknews-feed"})
            return self.web(request)
        self.app.state.news.http = httpx.Client(transport=httpx.MockTransport(transport))
        self.llm.responses = [evaluation(9), evaluation(6)]

        self.daily()

        self.assertEqual(len(self.candidates()), 2)
