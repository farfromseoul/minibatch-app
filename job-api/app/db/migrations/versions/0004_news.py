"""IT 뉴스 후보 (D40)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_item",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("gn_url", sa.String(300), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("gn_summary", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("readable", sa.Boolean(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("quality", sa.Text(), nullable=True),
        sa.Column("copyright_risk", sa.String(10), nullable=True),
        sa.Column("copyright", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("picked_at", sa.DateTime(), nullable=True),
        sa.Column("job_id", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_news_item_status", "news_item", ["status"])


def downgrade() -> None:
    op.drop_index("ix_news_item_status", table_name="news_item")
    op.drop_table("news_item")
