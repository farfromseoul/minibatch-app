"""topic 단계: 주제를 확정하고 job.json 을 쓴다 (앱 설계 "단계 계약", "job.json").

이후 단계는 DB 대신 이 파일만 읽는다 (아키텍처 D3). 시리즈 화이면 앞 화 줄거리를 함께 넣는다 (D24).
"""
from __future__ import annotations

import datetime as dt

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
# 최신 검색 (목록형 v1.4 L24): 요청 이름 research 에만 중계기가 웹 검색을 켠다 (llm-bridge BRIDGE_SEARCH_SCHEMAS)
_S = {"type": "string"}
RESEARCH_SCHEMA = {"type": "object", "properties": {
    "candidates": {"type": "array", "minItems": 1, "maxItems": 15, "items": {
        "type": "object", "properties": {"name": _S, "why": _S, "source": _S}, "required": ["name", "why", "source"],
        "additionalProperties": False}},
    "facts": {"type": "array", "items": _S, "minItems": 3, "maxItems": 20},
    "sources": {"type": "array", "minItems": 1, "maxItems": 8, "items": {
        "type": "object", "properties": {"title": _S, "url": _S}, "required": ["title", "url"], "additionalProperties": False}}},
    "required": ["candidates", "facts", "sources"], "additionalProperties": False}


def check_research(d, n: int) -> list[str]:
    if not isinstance(d, dict):
        return ["JSON 객체가 필요하다"]
    out = []
    if len(d.get("candidates") or []) < n:
        out.append(f"candidates 는 {n}개 이상(영상 항목 수)")
    if len(d.get("facts") or []) < 3:
        out.append("facts 를 3개 이상")
    if not any(str(x.get("url", "")).startswith(("http://", "https://")) for x in d.get("sources") or [] if isinstance(x, dict)):
        out.append("sources 에 실제로 본 http 주소를 1개 이상")
    return out


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
        target = int(cat.get("target_duration_sec") or 60)
        dur = (cat.get("listicle") or {}).get("duration") or {}
        if listicle and dur:  # 목록형 길이는 개수에 따라 (v1.4 L26): base + per_item × N
            target = round(float(dur.get("base", 22)) + float(dur.get("per_item", 8)) * (len(listicle["items"]) or listicle["count"]))
        review = None
        if (job.get("input") or {}).get("review"):  # 실습 리뷰 (D46): 웹 검색으로 기능 확인 + 과제 계획 (실행은 승인 뒤 lab 단계)
            from .handson import make_plan
            review = make_plan(ctx, job["topic"], job["input"]["review"], cat)
            rdur = (cat.get("review_video") or {}).get("duration") or {}
            target = round(float(rdur.get("base", 30)) + float(rdur.get("per_task", 20)) * len(review["tasks"]))
        ctx.write_json("job.json", {
            "jobId": job["id"],
            "topic": job["topic"],
            "topicKey": job["topicKey"],
            "language": "ko",
            "targetDurationSec": target,
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
            "review": review,
        })

    def _listicle(self, ctx: StepContext, topic: str, req):
        """목록형 쇼츠(D42): 참고 자료가 있으면 읽어 사실 목록을 만든다. 원문은 겹침 검사용으로 작업 폴더에만 둔다"""
        if not req:
            return None
        refs = [str(u) for u in (req.get("references") or [])][:MAX_REFERENCES]
        out = {"count": int(req.get("count") or 5), "items": [str(i) for i in req.get("items") or []], "facts": [], "sources": [],
               "research": bool(req.get("research")), "candidates": []}
        if out["research"] and not out["items"]:
            self._research(ctx, topic, out)
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
        out["facts"] = [str(f) for f in res.data["facts"]] + out["facts"]
        out["sources"] = [{"url": u} for u, _ in texts] + out["sources"]
        return out

    def _research(self, ctx: StepContext, topic: str, out: dict) -> None:
        """웹 검색으로 지금 후보·사실·출처 (v1.4 L24). 실패하거나 검색 없는 대체 모델이 답하면 기록만 하고 검색 없이 계속한다"""
        from .listicle import used_items
        used = used_items(ctx, topic)
        today = dt.date.today().isoformat()
        messages, _ = render_messages("research", topic=topic, count=out["count"], today=today,
                                      used=(", ".join(used) if used else "없음"))
        try:
            res = ask(ctx, messages, RESEARCH_SCHEMA, "research", lambda d: check_research(d, out["count"]))
        except StepFailure as e:
            ctx.note_degraded(f"최신 검색 실패({e.message[:120]}), 검색 없이 만든다")
            return
        model = (res.result.model if res.result else "") or ""
        if model.startswith("fallback:"):  # 중계기가 로컬 LLM 으로 넘겼다: 웹 검색이 없어 출처를 지어냈을 수 있다
            ctx.note_degraded(f"최신 검색을 대체 모델({model})이 답해 버렸다. 검색 없이 만든다")
            return
        if res.problems:
            ctx.note_degraded("최신 검색 답이 규칙에 맞지 않아 버렸다: " + "; ".join(res.problems)[:200])
            return
        d = res.data
        out["candidates"] = [{k: str(c.get(k) or "") for k in ("name", "why", "source")} for c in d["candidates"]]
        out["facts"] = [str(f) for f in d["facts"]]
        out["sources"] = [{"url": str(x["url"]), "title": str(x.get("title") or "")} for x in d["sources"]
                          if str(x.get("url", "")).startswith(("http://", "https://"))]
        out["researchedAt"] = today

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
