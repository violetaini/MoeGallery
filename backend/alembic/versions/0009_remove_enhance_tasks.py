"""remove image enhancement tasks

Revision ID: 0009_remove_enhance_tasks
Revises: 0008_image_enhancement_tasks
Create Date: 2026-07-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0009_remove_enhance_tasks"
down_revision: str | None = "0008_image_enhancement_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table("image_enhancement_tasks"):
        return
    if bind.dialect.name in {"mysql", "mariadb"}:
        op.drop_table("image_enhancement_tasks")
        return
    op.drop_index(op.f("ix_image_enhancement_tasks_status"), table_name="image_enhancement_tasks")
    op.drop_index(op.f("ix_image_enhancement_tasks_source_image_id"), table_name="image_enhancement_tasks")
    op.drop_index(op.f("ix_image_enhancement_tasks_result_image_id"), table_name="image_enhancement_tasks")
    op.drop_index(op.f("ix_image_enhancement_tasks_id"), table_name="image_enhancement_tasks")
    op.drop_index(op.f("ix_image_enhancement_tasks_created_at"), table_name="image_enhancement_tasks")
    op.drop_table("image_enhancement_tasks")


def downgrade() -> None:
    op.create_table(
        "image_enhancement_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_image_id", sa.Integer(), nullable=False),
        sa.Column("result_image_id", sa.Integer(), nullable=True),
        sa.Column("method", sa.String(length=40), nullable=False),
        sa.Column("scale", sa.Integer(), nullable=False),
        sa.Column("denoise", sa.String(length=20), nullable=False),
        sa.Column("sharpen", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["result_image_id"], ["images.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_image_id"], ["images.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_image_enhancement_tasks_created_at"), "image_enhancement_tasks", ["created_at"], unique=False)
    op.create_index(op.f("ix_image_enhancement_tasks_id"), "image_enhancement_tasks", ["id"], unique=False)
    op.create_index(
        op.f("ix_image_enhancement_tasks_result_image_id"),
        "image_enhancement_tasks",
        ["result_image_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_image_enhancement_tasks_source_image_id"),
        "image_enhancement_tasks",
        ["source_image_id"],
        unique=False,
    )
    op.create_index(op.f("ix_image_enhancement_tasks_status"), "image_enhancement_tasks", ["status"], unique=False)
