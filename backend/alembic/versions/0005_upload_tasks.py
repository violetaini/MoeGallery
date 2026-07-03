"""add upload task queue

Revision ID: 0005_upload_tasks
Revises: 0004_image_hdr_metadata
Create Date: 2026-06-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_upload_tasks"
down_revision: str | None = "0004_image_hdr_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "upload_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("staged_path", sa.String(length=500), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating", sa.String(length=20), nullable=False, server_default="safe"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("artist_name", sa.String(length=255), nullable=True),
        sa.Column("work_ids_csv", sa.Text(), nullable=True),
        sa.Column("character_ids_csv", sa.Text(), nullable=True),
        sa.Column("image_id", sa.Integer(), nullable=True),
        sa.Column("duplicate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_upload_tasks_id"), "upload_tasks", ["id"], unique=False)
    op.create_index(op.f("ix_upload_tasks_status"), "upload_tasks", ["status"], unique=False)
    op.create_index(op.f("ix_upload_tasks_image_id"), "upload_tasks", ["image_id"], unique=False)
    op.create_index(op.f("ix_upload_tasks_created_at"), "upload_tasks", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_upload_tasks_created_at"), table_name="upload_tasks")
    op.drop_index(op.f("ix_upload_tasks_image_id"), table_name="upload_tasks")
    op.drop_index(op.f("ix_upload_tasks_status"), table_name="upload_tasks")
    op.drop_index(op.f("ix_upload_tasks_id"), table_name="upload_tasks")
    op.drop_table("upload_tasks")
