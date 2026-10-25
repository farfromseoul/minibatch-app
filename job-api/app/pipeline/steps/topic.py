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
        ctx.write_json("job.json", {
            "jobId": job["id"],
            "topic": job["topic"],
            "topicKey": job["topicKey"],
            "language": "ko",
            "targetDurationSec": 60,
            "videoEngine": "remotion",
            "resolution": {"width": 1080, "height": 1920},
            "fps": 30,
            "theme": str(load_category(ctx.settings, job["category"]).get("theme") or "default"),  # 화면 스타일 (카테고리)
            "publish": {"platform": "youtube", "visibility": "private"},
            "category": job["category"],
            "series": series,
            "news": news,
        })

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
