"""add image orientation

Revision ID: 0010_image_orientation
Revises: 0009_remove_enhance_tasks
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "0010_image_orientation"
down_revision: str | None = "0009_remove_enhance_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("images")}
    if "orientation" not in columns:
        op.add_column(
            "images",
            sa.Column("orientation", sa.String(length=20), nullable=False, server_default="square"),
        )

    bind.execute(
        text(
            """
            UPDATE images
            SET orientation = CASE
                WHEN width > height THEN 'landscape'
                WHEN height > width THEN 'portrait'
                ELSE 'square'
            END
            """
        )
    )

    indexes = {index["name"] for index in inspector.get_indexes("images")}
    if "ix_images_orientation" not in indexes:
        op.create_index(op.f("ix_images_orientation"), "images", ["orientation"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("images")}
    if "ix_images_orientation" in indexes:
        op.drop_index(op.f("ix_images_orientation"), table_name="images")
    columns = {column["name"] for column in inspector.get_columns("images")}
    if "orientation" in columns:
        op.drop_column("images", "orientation")
