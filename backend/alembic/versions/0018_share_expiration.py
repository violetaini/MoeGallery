"""add share expiration

Revision ID: 0018_share_expiration
Revises: 0017_image_shares
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0018_share_expiration"
down_revision: str | None = "0017_image_shares"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("shares", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.create_index("ix_shares_expires_at", "shares", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_shares_expires_at", table_name="shares")
    op.drop_column("shares", "expires_at")
