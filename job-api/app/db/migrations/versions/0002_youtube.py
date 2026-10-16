"""YouTube 게시 칸: 시리즈 재생목록(D26 ②), 올린 영상 파일 해시 (작업 순서 20-d3)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("series", sa.Column("youtube_playlist_id", sa.String(64), nullable=True))
    op.add_column("publication", sa.Column("uploaded_sha256", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("publication") as t:
        t.drop_column("uploaded_sha256")
    with op.batch_alter_table("series") as t:
        t.drop_column("youtube_playlist_id")
