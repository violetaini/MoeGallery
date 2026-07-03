"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("thumbnail_path", sa.String(length=500), nullable=True),
        sa.Column("preview_path", sa.String(length=500), nullable=True),
        sa.Column("width", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("phash", sa.String(length=128), nullable=True),
        sa.Column("rating", sa.String(length=20), nullable=False, server_default="safe"),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("artist_name", sa.String(length=255), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("favorite_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sha256"),
    )
    op.create_index(op.f("ix_images_id"), "images", ["id"])
    op.create_index(op.f("ix_images_sha256"), "images", ["sha256"])
    op.create_index(op.f("ix_images_phash"), "images", ["phash"])
    op.create_index(op.f("ix_images_rating"), "images", ["rating"])
    op.create_index(op.f("ix_images_is_public"), "images", ["is_public"])
    op.create_index(op.f("ix_images_artist_name"), "images", ["artist_name"])
    op.create_index(op.f("ix_images_created_at"), "images", ["created_at"])

    op.create_table(
        "works",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=True),
        sa.Column("aliases", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_image_id", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cover_image_id"], ["images.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_works_id"), "works", ["id"])
    op.create_index(op.f("ix_works_name"), "works", ["name"])
    op.create_index(op.f("ix_works_sort_order"), "works", ["sort_order"])
    op.create_index(op.f("ix_works_created_at"), "works", ["created_at"])

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False, server_default="general"),
        sa.Column("aliases", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_tags_id"), "tags", ["id"])
    op.create_index(op.f("ix_tags_name"), "tags", ["name"])
    op.create_index(op.f("ix_tags_type"), "tags", ["type"])
    op.create_index(op.f("ix_tags_created_at"), "tags", ["created_at"])

    op.create_table(
        "characters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("work_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=True),
        sa.Column("aliases", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("avatar_image_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["avatar_image_id"], ["images.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_id"], ["works.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_characters_id"), "characters", ["id"])
    op.create_index(op.f("ix_characters_name"), "characters", ["name"])
    op.create_index(op.f("ix_characters_work_id"), "characters", ["work_id"])
    op.create_index(op.f("ix_characters_created_at"), "characters", ["created_at"])

    op.create_table(
        "image_works",
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("work_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_id"], ["works.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("image_id", "work_id"),
    )
    op.create_table(
        "image_characters",
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("image_id", "character_id"),
    )
    op.create_table(
        "image_tags",
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("image_id", "tag_id"),
    )


def downgrade() -> None:
    op.drop_table("image_tags")
    op.drop_table("image_characters")
    op.drop_table("image_works")
    op.drop_index(op.f("ix_characters_created_at"), table_name="characters")
    op.drop_index(op.f("ix_characters_work_id"), table_name="characters")
    op.drop_index(op.f("ix_characters_name"), table_name="characters")
    op.drop_index(op.f("ix_characters_id"), table_name="characters")
    op.drop_table("characters")
    op.drop_index(op.f("ix_tags_created_at"), table_name="tags")
    op.drop_index(op.f("ix_tags_type"), table_name="tags")
    op.drop_index(op.f("ix_tags_name"), table_name="tags")
    op.drop_index(op.f("ix_tags_id"), table_name="tags")
    op.drop_table("tags")
    op.drop_index(op.f("ix_works_created_at"), table_name="works")
    op.drop_index(op.f("ix_works_sort_order"), table_name="works")
    op.drop_index(op.f("ix_works_name"), table_name="works")
    op.drop_index(op.f("ix_works_id"), table_name="works")
    op.drop_table("works")
    op.drop_index(op.f("ix_images_created_at"), table_name="images")
    op.drop_index(op.f("ix_images_artist_name"), table_name="images")
    op.drop_index(op.f("ix_images_is_public"), table_name="images")
    op.drop_index(op.f("ix_images_rating"), table_name="images")
    op.drop_index(op.f("ix_images_phash"), table_name="images")
    op.drop_index(op.f("ix_images_sha256"), table_name="images")
    op.drop_index(op.f("ix_images_id"), table_name="images")
    op.drop_table("images")

