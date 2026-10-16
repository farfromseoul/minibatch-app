"""topic 단계: 주제를 확정하고 job.json 을 쓴다 (앱 설계 "단계 계약", "job.json").

이후 단계는 DB 대신 이 파일만 읽는다 (아키텍처 D3). 시리즈 화이면 앞 화 줄거리를 함께 넣는다 (D24).
"""
from __future__ import annotations

from app.domain.series import story_for

from .base import StepContext


class TopicStep:
    name = "topic"
    inputs: list[str] = []  # 입력은 DB 의 작업 정보
    outputs = ["job.json"]

    def run(self, ctx: StepContext) -> None:
        job = ctx.job
        series = None
        if job["seriesId"]:
            with ctx.db() as s:
                series = story_for(s, job["seriesId"], job["episodeNumber"])
        ctx.write_json("job.json", {
            "jobId": job["id"],
            "topic": job["topic"],
            "topicKey": job["topicKey"],
            "language": "ko",
            "targetDurationSec": 60,
            "videoEngine": "remotion",
            "resolution": {"width": 1080, "height": 1920},
            "fps": 30,
            "theme": "default",
            "publish": {"platform": "youtube", "visibility": "private"},
            "category": job["category"],
            "series": series,
        })
