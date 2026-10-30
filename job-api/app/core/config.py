"""설정. 값은 환경 변수에서 읽고(compose.yaml), 비밀 값은 파일 경로로만 받는다."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    token_file: Path
    content_dir: Path
    daily_job_limit: int = 3  # 아키텍처 D15
    review_backlog_limit: int = 6  # D15
    disk_free_warn_gb: int = 50
    # n8n Wait 노드 재개 주소만 부른다. 요청에 아무 주소나 넣어 job-api 가 외부로 요청을 보내게 하지 못하게
    resume_url_prefix: str = "http://n8n:5678/"
    # 텔레그램 /run 이 부르는 n8n 1번 생산 웹훅 (2026-10-31). compose 내부망 주소라 밖에서는 닿지 않는다
    produce_webhook_url: str = "http://n8n:5678/webhook/minibatch-produce-now"
    duplicate_window_days: int = 30  # 기획서 성공 기준 9
    # 제공자 설정 파일. None 이면 읽지 않는다(LLM 단계는 실패). 실제 서버는 환경 변수로 늘 지정한다
    providers_file: Path | None = None
    # 렌더링은 항상 Remotion (D5) 이라 제공자가 아닌 고정 주소다
    render_worker_url: str = "http://render-worker:8091"
    render_timeout_sec: int = 1800
    # YouTube: 클라이언트 파일(compose secret)과 갱신 토큰 파일(폴더째 붙인다, 아키텍처 "비밀 값"). 실행계획 15번에서 만든다
    youtube_client_file: Path = Path("/run/secrets/youtube_client")
    youtube_token_file: Path = Path("/run/minibatch/youtube-token/youtube_token.json")
    # 텔레그램 승인 (D28). 토큰 파일이나 chat id 가 없으면 이 기능만 꺼진다. chat id 는 비밀 값이 아니다
    telegram_token_file: Path = Path("/run/secrets/telegram_bot_token")
    telegram_chat_id: str = ""
    # ASMR 채널 (D38): 사용자가 넣은 영상을 승인받아 올린다. 인증 파일은 MiniBatch 와 따로(다른 Google Cloud 프로젝트)
    asmr_youtube_client_file: Path = Path("/run/minibatch/asmr-youtube/client_secret.json")
    asmr_youtube_token_file: Path = Path("/run/minibatch/asmr-youtube/youtube_token.json")
    asmr_channel_id: str = ""  # 비어 있으면 올리지 않는다(다른 채널에 올리는 사고 방지). 비밀 값이 아니다
    asmr_daily_upload_limit: int = 3
    # IT 뉴스 (D40): 하루 최대 고르는 편수, 한 번에 보내는 후보 수
    news_daily_max: int = 3
    news_candidates: int = 5
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        data_dir = Path(env.get("MINIBATCH_DATA_DIR", "/data"))
        return cls(
            data_dir=data_dir,
            db_path=Path(env.get("MINIBATCH_DB_PATH", str(data_dir / "db" / "minibatch.sqlite"))),
            token_file=Path(env.get("MINIBATCH_JOB_API_TOKEN_FILE", "/run/secrets/job_api_token")),
            content_dir=Path(env.get("MINIBATCH_CONTENT_DIR", "/app/content")),
            daily_job_limit=int(env.get("MINIBATCH_DAILY_JOB_LIMIT", "3")),
            review_backlog_limit=int(env.get("MINIBATCH_REVIEW_BACKLOG_LIMIT", "6")),
            disk_free_warn_gb=int(env.get("MINIBATCH_DISK_FREE_WARN_GB", "50")),
            resume_url_prefix=env.get("MINIBATCH_RESUME_URL_PREFIX", "http://n8n:5678/"),
            produce_webhook_url=env.get("MINIBATCH_PRODUCE_WEBHOOK_URL", "http://n8n:5678/webhook/minibatch-produce-now"),
            providers_file=Path(env.get("MINIBATCH_PROVIDERS_FILE", "/etc/minibatch/providers.yaml")),
            render_worker_url=env.get("MINIBATCH_RENDER_WORKER_URL", "http://render-worker:8091"),
            youtube_client_file=Path(env.get("MINIBATCH_YOUTUBE_CLIENT_FILE", "/run/secrets/youtube_client")),
            youtube_token_file=Path(env.get("MINIBATCH_YOUTUBE_TOKEN_FILE", "/run/minibatch/youtube-token/youtube_token.json")),
            telegram_token_file=Path(env.get("MINIBATCH_TELEGRAM_TOKEN_FILE", "/run/secrets/telegram_bot_token")),
            telegram_chat_id=env.get("MINIBATCH_TELEGRAM_CHAT_ID", ""),
            asmr_youtube_client_file=Path(env.get("MINIBATCH_ASMR_YOUTUBE_CLIENT_FILE", "/run/minibatch/asmr-youtube/client_secret.json")),
            asmr_youtube_token_file=Path(env.get("MINIBATCH_ASMR_YOUTUBE_TOKEN_FILE", "/run/minibatch/asmr-youtube/youtube_token.json")),
            asmr_channel_id=env.get("MINIBATCH_ASMR_CHANNEL_ID", ""),
            asmr_daily_upload_limit=int(env.get("MINIBATCH_ASMR_DAILY_UPLOAD_LIMIT", "3")),
            news_daily_max=int(env.get("MINIBATCH_NEWS_DAILY_MAX", "3")),
            news_candidates=int(env.get("MINIBATCH_NEWS_CANDIDATES", "5")),
        )

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def asmr_dir(self) -> Path:
        return self.data_dir / "asmr"

    def category_file(self, key: str) -> Path:
        return self.content_dir / "categories" / f"{key}.yaml"
