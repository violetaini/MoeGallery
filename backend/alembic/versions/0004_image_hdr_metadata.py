"""add image hdr metadata

Revision ID: 0004_image_hdr_metadata
Revises: 0003_app_settings
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_image_hdr_metadata"
down_revision: str | None = "0003_app_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "images",
        sa.Column("is_animated", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "images",
        sa.Column("dynamic_range", sa.String(length=20), nullable=False, server_default=sa.text("'sdr'")),
    )
    op.add_column(
        "images",
        sa.Column("bit_depth", sa.Integer(), nullable=False, server_default=sa.text("8")),
    )
    op.add_column("images", sa.Column("color_profile", sa.String(length=120), nullable=True))
    op.create_index(op.f("ix_images_is_animated"), "images", ["is_animated"], unique=False)
    op.create_index(op.f("ix_images_dynamic_range"), "images", ["dynamic_range"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_images_dynamic_range"), table_name="images")
    op.drop_index(op.f("ix_images_is_animated"), table_name="images")
    op.drop_column("images", "color_profile")
    op.drop_column("images", "bit_depth")
    op.drop_column("images", "dynamic_range")
    op.drop_column("images", "is_animated")
