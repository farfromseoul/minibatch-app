"""Alembic 이전 파일이 코드의 테이블 정의와 같은지 확인한다."""
import pathlib
import tempfile
import unittest

from sqlalchemy import create_engine


class MigrationTest(unittest.TestCase):
    def test_upgrade_head_matches_models(self):
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext

        from app.db.migrate import upgrade
        from app.db.models import Base

        with tempfile.TemporaryDirectory() as tmp:
            url = f"sqlite:///{pathlib.Path(tmp) / 'm.sqlite'}"
            upgrade(url)
            engine = create_engine(url)
            with engine.connect() as conn:
                diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
            engine.dispose()

        self.assertEqual(diff, [])

    def test_upgrade_twice_is_harmless(self):
        from app.db.migrate import upgrade

        with tempfile.TemporaryDirectory() as tmp:
            url = f"sqlite:///{pathlib.Path(tmp) / 'm.sqlite'}"
            upgrade(url)
            upgrade(url)


if __name__ == "__main__":
    unittest.main()
