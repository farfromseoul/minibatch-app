"""Alembic 실행 환경. app/db/migrate.py 의 upgrade() 가 주소를 넣어 부른다."""
from alembic import context
from sqlalchemy import create_engine

from app.db.models import Base

config = context.config


def run() -> None:
    url = config.get_main_option("sqlalchemy.url")
    engine = create_engine(url)
    with engine.connect() as conn:
        # SQLite 는 ALTER TABLE 이 제한적이라 batch 모드로 컬럼 변경을 처리한다
        context.configure(connection=conn, target_metadata=Base.metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run()
