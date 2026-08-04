"""add API key policies

Revision ID: 0011_api_key_policies
Revises: 0010_image_orientation
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0011_api_key_policies"
down_revision: str | None = "0010_image_orientation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "api_key_policies" in inspector.get_table_names():
        return
    op.create_table(
        "api_key_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("scopes_json", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index(op.f("ix_api_key_policies_id"), "api_key_policies", ["id"], unique=False)
    op.create_index(op.f("ix_api_key_policies_key_hash"), "api_key_policies", ["key_hash"], unique=True)
    op.create_index(op.f("ix_api_key_policies_expires_at"), "api_key_policies", ["expires_at"], unique=False)
    op.create_index(op.f("ix_api_key_policies_revoked_at"), "api_key_policies", ["revoked_at"], unique=False)
    op.create_index(op.f("ix_api_key_policies_created_at"), "api_key_policies", ["created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if "api_key_policies" in inspect(bind).get_table_names():
        op.drop_table("api_key_policies")
