"""add upload queue reliability fields

Revision ID: 0013_upload_queue_reliability
Revises: 0012_upload_task_preflight
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0013_upload_queue_reliability"
down_revision: str | None = "0012_upload_task_preflight"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"]: column for column in inspector.get_columns("upload_tasks")}
    additions = (
        ("attempt_count", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0")),
        ("max_attempts", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3")),
        ("next_attempt_at", sa.Column("next_attempt_at", sa.DateTime(), nullable=True)),
        ("worker_id", sa.Column("worker_id", sa.String(length=120), nullable=True)),
        ("lease_token", sa.Column("lease_token", sa.String(length=64), nullable=True)),
        ("lease_expires_at", sa.Column("lease_expires_at", sa.DateTime(), nullable=True)),
        ("heartbeat_at", sa.Column("heartbeat_at", sa.DateTime(), nullable=True)),
        ("cancel_requested", sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false())),
        ("error_code", sa.Column("error_code", sa.String(length=80), nullable=True)),
        ("staged_file_deleted_at", sa.Column("staged_file_deleted_at", sa.DateTime(), nullable=True)),
    )
    for name, column in additions:
        if name not in columns:
            op.add_column("upload_tasks", column)

    if not columns["staged_path"].get("nullable", True):
        with op.batch_alter_table("upload_tasks") as batch_op:
            batch_op.alter_column(
                "staged_path",
                existing_type=sa.String(length=500),
                nullable=True,
            )

    index_names = {index["name"] for index in inspect(bind).get_indexes("upload_tasks")}
    if "ix_upload_tasks_next_attempt_at" not in index_names:
        op.create_index("ix_upload_tasks_next_attempt_at", "upload_tasks", ["next_attempt_at"], unique=False)
    if "ix_upload_tasks_lease_token" not in index_names:
        op.create_index("ix_upload_tasks_lease_token", "upload_tasks", ["lease_token"], unique=False)
    if "ix_upload_tasks_lease_expires_at" not in index_names:
        op.create_index("ix_upload_tasks_lease_expires_at", "upload_tasks", ["lease_expires_at"], unique=False)
    if "ix_upload_tasks_status_next_attempt" not in index_names:
        op.create_index(
            "ix_upload_tasks_status_next_attempt",
            "upload_tasks",
            ["status", "next_attempt_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    index_names = {index["name"] for index in inspect(bind).get_indexes("upload_tasks")}
    for index_name in (
        "ix_upload_tasks_status_next_attempt",
        "ix_upload_tasks_lease_expires_at",
        "ix_upload_tasks_lease_token",
        "ix_upload_tasks_next_attempt_at",
    ):
        if index_name in index_names:
            op.drop_index(index_name, table_name="upload_tasks")

    columns = {column["name"] for column in inspect(bind).get_columns("upload_tasks")}
    bind.execute(sa.text("UPDATE upload_tasks SET staged_path = '' WHERE staged_path IS NULL"))
    removable = (
        "staged_file_deleted_at",
        "error_code",
        "cancel_requested",
        "heartbeat_at",
        "lease_expires_at",
        "lease_token",
        "worker_id",
        "next_attempt_at",
        "max_attempts",
        "attempt_count",
    )
    with op.batch_alter_table("upload_tasks") as batch_op:
        batch_op.alter_column(
            "staged_path",
            existing_type=sa.String(length=500),
            nullable=False,
        )
        for name in removable:
            if name in columns:
                batch_op.drop_column(name)
