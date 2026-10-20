"""ASMR 채널 가져온 영상 (D38)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-20
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asmr_video",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("file_name", sa.String(300), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("probe", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("video_id", sa.String(64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retry_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("upload_approved_at", sa.DateTime(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("notified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_asmr_video_status", "asmr_video", ["status"])


def downgrade() -> None:
    op.drop_index("ix_asmr_video_status", table_name="asmr_video")
    op.drop_table("asmr_video")
