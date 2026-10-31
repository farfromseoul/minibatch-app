"""topic 단계: 주제를 확정하고 job.json 을 쓴다 (앱 설계 "단계 계약", "job.json").

이후 단계는 DB 대신 이 파일만 읽는다 (아키텍처 D3). 시리즈 화이면 앞 화 줄거리를 함께 넣는다 (D24).
"""
from __future__ import annotations

from app.core.category import load_category
from app.domain.series import story_for
from app.llm.prompting import render_messages

from .base import StepContext, StepFailure
from .llm_common import ask

FACTS_SCHEMA = {"type": "object", "properties": {
    "facts": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 12},
    "angle": {"type": "string"}, "source_title": {"type": "string"}},
    "required": ["facts", "angle", "source_title"], "additionalProperties": False}


MAX_REFERENCES = 5
MAX_SOURCE_CHARS = 6000  # 참고 자료 하나에서 LLM 에 넣는 글자 수
REF_FACTS_SCHEMA = {"type": "object", "properties": {
    "facts": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 15}},
    "required": ["facts"], "additionalProperties": False}


class TopicStep:
    name = "topic"
    inputs: list[str] = []  # 입력은 DB 의 작업 정보
    outputs = ["job.json"]

    def __init__(self, news=None):
        self.news = news  # IT 뉴스 원문 읽기 (NewsService, D40). 없으면 뉴스 작업을 만들지 못한다

    def run(self, ctx: StepContext) -> None:
        job = ctx.job
        series = None
        if job["seriesId"]:
            with ctx.db() as s:
                series = story_for(s, job["seriesId"], job["episodeNumber"], settings=ctx.settings)
        news = self._news(ctx, (job.get("input") or {}).get("news"))
        cat = load_category(ctx.settings, job["category"])
        listicle = self._listicle(ctx, job["topic"], (job.get("input") or {}).get("listicle"))
        ctx.write_json("job.json", {
            "jobId": job["id"],
            "topic": job["topic"],
            "topicKey": job["topicKey"],
            "language": "ko",
            "targetDurationSec": int(cat.get("target_duration_sec") or 60),  # 목록형 45초 (D42)
            "durationToleranceSec": int(cat.get("duration_tolerance_sec") or 5),
            "format": str(cat.get("format") or "explainer"),
            "videoEngine": "remotion",
            "resolution": {"width": 1080, "height": 1920},
            "fps": 30,
            # 화면 스타일: 카테고리 기본, 목록형은 작업 입력의 테마(추천·버튼·직접, v1.3)
            "theme": str(((job.get("input") or {}).get("listicle") or {}).get("theme") or cat.get("theme") or "default"),
            "publish": {"platform": "youtube", "visibility": "private"},
            "category": job["category"],
            "series": series,
            "news": news,
            "listicle": listicle,
        })

    def _listicle(self, ctx: StepContext, topic: str, req):
        """목록형 쇼츠(D42): 참고 자료가 있으면 읽어 사실 목록을 만든다. 원문은 겹침 검사용으로 작업 폴더에만 둔다"""
        if not req:
            return None
        refs = [str(u) for u in (req.get("references") or [])][:MAX_REFERENCES]
        out = {"count": int(req.get("count") or 5), "items": [str(i) for i in req.get("items") or []], "facts": [], "sources": []}
        if not refs:
            return out
        if self.news is None:
            raise StepFailure("deterministic", "참고 자료 읽기(NewsService)가 꺼져 있다")
        texts, unread = [], []
        for url in refs:
            text = self.news.fetch_article(url)
            if text is None:
                unread.append(url)
                continue
            texts.append((url, text[:MAX_SOURCE_CHARS]))
        if not texts:
            raise StepFailure("deterministic", "참고 자료를 하나도 읽지 못했다: " + ", ".join(refs) + ". 다른 주소로, 또는 참고 자료 없이 /top")
        if unread:
            ctx.note_degraded("읽지 못한 참고 자료: " + ", ".join(unread))
        ctx.write_text("listicle_sources.txt", "\n\n".join(t for _, t in texts))
        source = "\n\n".join(f"[자료 {i}] {u}\n{t}" for i, (u, t) in enumerate(texts, start=1))
        messages, _ = render_messages("ref_facts", topic=topic, source=source)
        res = ask(ctx, messages, REF_FACTS_SCHEMA, "ref_facts",
                  lambda d: [] if isinstance(d, dict) and len(d.get("facts") or []) >= 3 else ["facts 를 3개 이상"])
        if res.problems:
            raise StepFailure("deterministic", "참고 자료 사실 목록을 만들지 못했다: " + "; ".join(res.problems))
        out["facts"] = [str(f) for f in res.data["facts"]]
        out["sources"] = [{"url": u} for u, _ in texts]
        return out

    def _news(self, ctx: StepContext, news):
        """IT 뉴스: 원문을 읽어 영상에 쓸 사실 목록을 만든다. 원문(과 GeekNews 요약)은 겹침 검사용으로 작업 폴더에만 둔다"""
        if not news:
            return None
        text = self.news.fetch_article(news.get("sourceUrl")) if self.news is not None else None
        if text is None:
            raise StepFailure("deterministic", f"원문을 읽지 못했다: {news.get('sourceUrl')}. 다른 후보를 고른다")
        ctx.write_text("news_source.txt", text + "\n\n" + (news.get("gnSummary") or ""))
        messages, _ = render_messages("news_facts", title=news["title"], source=text[:8000])
        out = ask(ctx, messages, FACTS_SCHEMA, "news_facts",
                  lambda d: [] if isinstance(d, dict) and len(d.get("facts") or []) >= 3 else ["facts 를 3개 이상"])
        if out.problems:
            raise StepFailure("deterministic", "원문 사실 목록을 만들지 못했다: " + "; ".join(out.problems))
        return {"id": news["id"], "title": news["title"], "sourceUrl": news["sourceUrl"], "gnUrl": news["gnUrl"],
                "sourceTitle": str(out.data["source_title"]), "facts": [str(f) for f in out.data["facts"]],
                "angle": str(out.data["angle"])}
