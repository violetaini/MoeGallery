"""add admin sessions

Revision ID: 0007_admin_sessions
Revises: 0006_upload_task_duplicate_merge_flag
Create Date: 2026-07-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0007_admin_sessions"
down_revision: str | None = "0006_upload_task_duplicate_merge_flag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "admin_sessions" in inspector.get_table_names():
        existing_indexes = {index["name"] for index in inspector.get_indexes("admin_sessions")}
        for name, columns in {
            "ix_admin_sessions_id": ["id"],
            "ix_admin_sessions_username": ["username"],
            "ix_admin_sessions_revoked_at": ["revoked_at"],
            "ix_admin_sessions_expires_at": ["expires_at"],
            "ix_admin_sessions_created_at": ["created_at"],
        }.items():
            if name not in existing_indexes:
                op.create_index(name, "admin_sessions", columns, unique=False)
        return
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_admin_sessions_id"), "admin_sessions", ["id"], unique=False)
    op.create_index(op.f("ix_admin_sessions_username"), "admin_sessions", ["username"], unique=False)
    op.create_index(op.f("ix_admin_sessions_revoked_at"), "admin_sessions", ["revoked_at"], unique=False)
    op.create_index(op.f("ix_admin_sessions_expires_at"), "admin_sessions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_admin_sessions_created_at"), "admin_sessions", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_sessions_created_at"), table_name="admin_sessions")
    op.drop_index(op.f("ix_admin_sessions_expires_at"), table_name="admin_sessions")
    op.drop_index(op.f("ix_admin_sessions_revoked_at"), table_name="admin_sessions")
    op.drop_index(op.f("ix_admin_sessions_username"), table_name="admin_sessions")
    op.drop_index(op.f("ix_admin_sessions_id"), table_name="admin_sessions")
    op.drop_table("admin_sessions")
