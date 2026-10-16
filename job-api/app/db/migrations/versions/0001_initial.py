"""처음 테이블 (아키텍처 데이터 모델 + D23~D25 시리즈·주제 출처)

Revision ID: 0001
Revises:
Create Date: 2026-10-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topic",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("normalized_key", sa.String(200), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("normalized_key"),
    )
    op.create_table(
        "series",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("bible", sa.JSON(), nullable=False),
        sa.Column("plan_source", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "job",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topic.id"), nullable=True),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("topic_key", sa.String(200), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("series_id", sa.String(64), sa.ForeignKey("series.id"), nullable=True),
        sa.Column("episode_number", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("current_step", sa.String(20), nullable=True),
        sa.Column("video_engine", sa.String(20), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_job_topic_key", "job", ["topic_key"])
    op.create_index("ix_job_status", "job", ["status"])
    op.create_table(
        "episode",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series_id", sa.String(64), sa.ForeignKey("series.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("outline", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("next_teaser", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("job_id", sa.String(32), sa.ForeignKey("job.id"), nullable=True),
        sa.UniqueConstraint("series_id", "number", name="uq_episode_series_number"),
    )
    op.create_table(
        "step_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(32), sa.ForeignKey("job.id"), nullable=False),
        sa.Column("step", sa.String(20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(20), nullable=True),
        sa.Column("retry_from", sa.String(20), nullable=True),
        sa.Column("retry_at", sa.String(40), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("superseded", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("job_id", "step", "attempt", name="uq_step_run_attempt"),
    )
    op.create_table(
        "artifact",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(32), sa.ForeignKey("job.id"), nullable=False),
        sa.Column("step", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("path", sa.String(300), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("superseded", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "job_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(32), sa.ForeignKey("job.id"), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "publication",
        sa.Column("job_id", sa.String(32), sa.ForeignKey("job.id"), primary_key=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("video_id", sa.String(64), nullable=True),
        sa.Column("visibility", sa.String(20), nullable=False),
        sa.Column("publish_at", sa.DateTime(), nullable=True),
        sa.Column("contains_synthetic_media", sa.Boolean(), nullable=True),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    for table in ("publication", "job_event", "artifact", "step_run", "episode"):
        op.drop_table(table)
    op.drop_index("ix_job_status", "job")
    op.drop_index("ix_job_topic_key", "job")
    for table in ("job", "series", "topic"):
        op.drop_table(table)
