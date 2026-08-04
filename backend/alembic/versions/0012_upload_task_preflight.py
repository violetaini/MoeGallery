"""add upload task preflight metadata

Revision ID: 0012_upload_task_preflight
Revises: 0011_api_key_policies
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0012_upload_task_preflight"
down_revision: str | None = "0011_api_key_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("upload_tasks")}
    if "sha256" not in columns:
        op.add_column("upload_tasks", sa.Column("sha256", sa.String(length=64), nullable=True))
        op.create_index(op.f("ix_upload_tasks_sha256"), "upload_tasks", ["sha256"], unique=False)
    if "inspection_json" not in columns:
        op.add_column("upload_tasks", sa.Column("inspection_json", sa.Text(), nullable=True))
    if "preflight_duplicate" not in columns:
        op.add_column(
            "upload_tasks",
            sa.Column("preflight_duplicate", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("upload_tasks")}
    if "preflight_duplicate" in columns:
        op.drop_column("upload_tasks", "preflight_duplicate")
    if "inspection_json" in columns:
        op.drop_column("upload_tasks", "inspection_json")
    if "sha256" in columns:
        op.drop_index(op.f("ix_upload_tasks_sha256"), table_name="upload_tasks")
        op.drop_column("upload_tasks", "sha256")
