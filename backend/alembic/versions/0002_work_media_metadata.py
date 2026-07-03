"""add work media metadata

Revision ID: 0002_work_media_metadata
Revises: 0001_initial_schema
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_work_media_metadata"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("works", sa.Column("backdrop_image_id", sa.Integer(), nullable=True))
    op.add_column("works", sa.Column("tagline", sa.String(length=500), nullable=True))
    op.add_column("works", sa.Column("production_year", sa.Integer(), nullable=True))
    op.add_column("works", sa.Column("run_time_minutes", sa.Integer(), nullable=True))
    op.add_column("works", sa.Column("community_rating", sa.Float(), nullable=True))
    op.add_column("works", sa.Column("content_rating", sa.String(length=80), nullable=True))
    op.add_column("works", sa.Column("genres", sa.Text(), nullable=True))
    op.add_column("works", sa.Column("studios", sa.Text(), nullable=True))
    op.add_column("works", sa.Column("official_site", sa.String(length=1000), nullable=True))
    op.add_column("works", sa.Column("status", sa.String(length=80), nullable=True))
    op.create_index(op.f("ix_works_production_year"), "works", ["production_year"])


def downgrade() -> None:
    op.drop_index(op.f("ix_works_production_year"), table_name="works")
    op.drop_column("works", "status")
    op.drop_column("works", "official_site")
    op.drop_column("works", "studios")
    op.drop_column("works", "genres")
    op.drop_column("works", "content_rating")
    op.drop_column("works", "community_rating")
    op.drop_column("works", "run_time_minutes")
    op.drop_column("works", "production_year")
    op.drop_column("works", "tagline")
    op.drop_column("works", "backdrop_image_id")
