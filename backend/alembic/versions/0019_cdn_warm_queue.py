"""add CDN warm queue

Revision ID: 0019_cdn_warm_queue
Revises: 0018_share_expiration
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0019_cdn_warm_queue"
down_revision: str | None = "0018_share_expiration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cdn_warm_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("variant", sa.String(length=20), nullable=False),
        sa.Column("media_version", sa.Integer(), nullable=False),
        sa.Column("target_url", sa.String(length=1200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("cache_status", sa.String(length=32), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("image_id", "variant", "media_version", name="uq_cdn_warm_tasks_image_variant_version"),
    )
    op.create_index("ix_cdn_warm_tasks_id", "cdn_warm_tasks", ["id"], unique=False)
    op.create_index("ix_cdn_warm_tasks_image_id", "cdn_warm_tasks", ["image_id"], unique=False)
    op.create_index("ix_cdn_warm_tasks_status", "cdn_warm_tasks", ["status"], unique=False)
    op.create_index("ix_cdn_warm_tasks_next_attempt_at", "cdn_warm_tasks", ["next_attempt_at"], unique=False)
    op.create_index("ix_cdn_warm_tasks_created_at", "cdn_warm_tasks", ["created_at"], unique=False)
    op.create_index("ix_cdn_warm_tasks_claim_ready", "cdn_warm_tasks", ["status", "next_attempt_at", "created_at", "id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_cdn_warm_tasks_claim_ready", table_name="cdn_warm_tasks")
    op.drop_index("ix_cdn_warm_tasks_created_at", table_name="cdn_warm_tasks")
    op.drop_index("ix_cdn_warm_tasks_next_attempt_at", table_name="cdn_warm_tasks")
    op.drop_index("ix_cdn_warm_tasks_status", table_name="cdn_warm_tasks")
    op.drop_index("ix_cdn_warm_tasks_image_id", table_name="cdn_warm_tasks")
    op.drop_index("ix_cdn_warm_tasks_id", table_name="cdn_warm_tasks")
    op.drop_table("cdn_warm_tasks")
