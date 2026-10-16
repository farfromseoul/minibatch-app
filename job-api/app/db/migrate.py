"""DB 이전(Alembic). job-api 가 시작할 때 최신 버전까지 올린다."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS = Path(__file__).parent / "migrations"


def alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def upgrade(url: str) -> None:
    command.upgrade(alembic_config(url), "head")
