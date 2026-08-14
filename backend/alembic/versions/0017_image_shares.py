"""add token based image shares

Revision ID: 0017_image_shares
Revises: 0016_structural_artwork_integrity
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0017_image_shares"
down_revision: str | None = "0016_structural_artwork_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shares",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shares_token", "shares", ["token"], unique=True)
    op.create_index("ix_shares_is_active", "shares", ["is_active"], unique=False)
    op.create_index("ix_shares_id", "shares", ["id"], unique=False)
    op.create_index("ix_shares_created_at", "shares", ["created_at"], unique=False)

    op.create_table(
        "share_images",
        sa.Column("share_id", sa.Integer(), nullable=False),
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["share_id"], ["shares.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("share_id", "image_id"),
    )
    op.create_index("ix_share_images_image_share", "share_images", ["image_id", "share_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_share_images_image_share", table_name="share_images")
    op.drop_table("share_images")
    op.drop_index("ix_shares_id", table_name="shares")
    op.drop_index("ix_shares_is_active", table_name="shares")
    op.drop_index("ix_shares_token", table_name="shares")
    op.drop_index("ix_shares_created_at", table_name="shares")
    op.drop_table("shares")
