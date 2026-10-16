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
    duplicate_window_days: int = 30  # 기획서 성공 기준 9
    # 제공자 설정 파일. None 이면 읽지 않는다(LLM 단계는 실패). 실제 서버는 환경 변수로 늘 지정한다
    providers_file: Path | None = None
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
            providers_file=Path(env.get("MINIBATCH_PROVIDERS_FILE", "/etc/minibatch/providers.yaml")),
        )

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    def category_file(self, key: str) -> Path:
        return self.content_dir / "categories" / f"{key}.yaml"
