"""단계 순서 (아키텍처 흐름 1). 순서는 n8n 이 지휘하고, 이 목록은 GET /pipeline 으로 내준다."""

PIPELINE = ["topic", "script", "review", "scenes", "tts", "timeline", "visuals", "render", "qc", "upload"]
