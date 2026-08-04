"""add media delivery version and lookup indexes

Revision ID: 0014_media_delivery_cache
Revises: 0013_upload_queue_reliability
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0014_media_delivery_cache"
down_revision: str | None = "0013_upload_queue_reliability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_index_if_missing(
    table_name: str,
    index_name: str,
    columns: list[str],
) -> None:
    bind = op.get_bind()
    index_names = {index["name"] for index in inspect(bind).get_indexes(table_name)}
    if index_name not in index_names:
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade() -> None:
    bind = op.get_bind()
    image_columns = {column["name"] for column in inspect(bind).get_columns("images")}
    if "media_version" not in image_columns:
        op.add_column(
            "images",
            sa.Column("media_version", sa.Integer(), nullable=False, server_default="1"),
        )

    _create_index_if_missing("images", "ix_images_file_path", ["file_path"])
    _create_index_if_missing("images", "ix_images_preview_path", ["preview_path"])
    _create_index_if_missing("images", "ix_images_thumbnail_path", ["thumbnail_path"])
    _create_index_if_missing(
        "images",
        "ix_images_public_rating_created",
        ["is_public", "rating", "created_at", "id"],
    )
    _create_index_if_missing("image_works", "ix_image_works_work_image", ["work_id", "image_id"])
    _create_index_if_missing(
        "image_characters",
        "ix_image_characters_character_image",
        ["character_id", "image_id"],
    )
    _create_index_if_missing("image_tags", "ix_image_tags_tag_image", ["tag_id", "image_id"])


def downgrade() -> None:
    bind = op.get_bind()
    index_tables = {
        "images": (
            "ix_images_public_rating_created",
            "ix_images_thumbnail_path",
            "ix_images_preview_path",
            "ix_images_file_path",
        ),
        "image_works": ("ix_image_works_work_image",),
        "image_characters": ("ix_image_characters_character_image",),
        "image_tags": ("ix_image_tags_tag_image",),
    }
    for table_name, names in index_tables.items():
        existing = {index["name"] for index in inspect(bind).get_indexes(table_name)}
        for index_name in names:
            if index_name in existing:
                op.drop_index(index_name, table_name=table_name)

    columns = {column["name"] for column in inspect(bind).get_columns("images")}
    if "media_version" in columns:
        op.drop_column("images", "media_version")
