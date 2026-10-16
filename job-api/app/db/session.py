"""SQLite 연결. 파일 하나짜리 DB 라 별도 서버가 없다 (아키텍처 D4)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # 단계 실행이 백그라운드 스레드에서 DB 를 쓰므로 스레드 확인을 끈다(세션은 스레드마다 따로 연다)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")  # 읽기와 쓰기가 서로 덜 막는다
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    return engine


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
