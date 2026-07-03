"""add upload task duplicate merge flag

Revision ID: 0006_upload_task_duplicate_merge_flag
Revises: 0005_upload_tasks
Create Date: 2026-06-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0006_upload_task_duplicate_merge_flag"
down_revision: str | None = "0005_upload_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("upload_tasks")}
    if "merge_duplicate_relations" in columns:
        return
    op.add_column(
        "upload_tasks",
        sa.Column("merge_duplicate_relations", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("upload_tasks", "merge_duplicate_relations")
