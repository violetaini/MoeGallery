"""add structural artwork integrity and lookup indexes

Revision ID: 0016_structural_artwork_integrity
Revises: 0015_database_concurrency
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "0016_structural_artwork_integrity"
down_revision: str | None = "0015_database_concurrency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BACKDROP_FOREIGN_KEY = "fk_works_backdrop_image_id_images"
LOOKUP_INDEXES = (
    ("works", "ix_works_cover_image_id", ["cover_image_id"]),
    ("works", "ix_works_backdrop_image_id", ["backdrop_image_id"]),
    ("characters", "ix_characters_avatar_image_id", ["avatar_image_id"]),
)
REDUNDANT_INDEXES = (
    ("images", "ix_images_sha256", ["sha256"]),
    ("tags", "ix_tags_name", ["name"]),
    ("upload_tasks", "ix_upload_tasks_status_next_attempt", ["status", "next_attempt_at"]),
)


def _has_leading_index(table_name: str, columns: list[str]) -> bool:
    for index in inspect(op.get_bind()).get_indexes(table_name):
        indexed_columns = list(index.get("column_names") or [])
        if indexed_columns[: len(columns)] == columns:
            return True
    return False


def _backdrop_foreign_key_name() -> str | None:
    for foreign_key in inspect(op.get_bind()).get_foreign_keys("works"):
        if (
            foreign_key.get("referred_table") == "images"
            and foreign_key.get("constrained_columns") == ["backdrop_image_id"]
        ):
            return foreign_key.get("name")
    return None


def _drop_index_if_present(table_name: str, index_name: str) -> None:
    index_names = {index["name"] for index in inspect(op.get_bind()).get_indexes(table_name)}
    if index_name in index_names:
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE works SET backdrop_image_id = NULL "
            "WHERE backdrop_image_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM images WHERE images.id = works.backdrop_image_id)"
        )
    )

    for table_name, index_name, columns in LOOKUP_INDEXES:
        if not _has_leading_index(table_name, columns):
            op.create_index(index_name, table_name, columns, unique=False)

    if _backdrop_foreign_key_name() is None:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("works") as batch_op:
                batch_op.create_foreign_key(
                    BACKDROP_FOREIGN_KEY,
                    "images",
                    ["backdrop_image_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
        else:
            op.create_foreign_key(
                BACKDROP_FOREIGN_KEY,
                "works",
                "images",
                ["backdrop_image_id"],
                ["id"],
                ondelete="SET NULL",
            )

    for table_name, index_name, _columns in REDUNDANT_INDEXES:
        _drop_index_if_present(table_name, index_name)


def downgrade() -> None:
    bind = op.get_bind()
    foreign_key_name = _backdrop_foreign_key_name()
    if foreign_key_name:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("works") as batch_op:
                batch_op.drop_constraint(foreign_key_name, type_="foreignkey")
        else:
            op.drop_constraint(foreign_key_name, "works", type_="foreignkey")

    for table_name, index_name, _columns in LOOKUP_INDEXES:
        _drop_index_if_present(table_name, index_name)

    for table_name, index_name, columns in REDUNDANT_INDEXES:
        index_names = {index["name"] for index in inspect(bind).get_indexes(table_name)}
        if index_name not in index_names:
            op.create_index(index_name, table_name, columns, unique=False)
