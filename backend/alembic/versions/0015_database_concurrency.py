"""add upload task claim index

Revision ID: 0015_database_concurrency
Revises: 0014_media_delivery_cache
Create Date: 2026-08-03
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect


revision: str = "0015_database_concurrency"
down_revision: str | None = "0014_media_delivery_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INDEX_NAME = "ix_upload_tasks_claim_ready"
INDEX_COLUMNS = ["status", "cancel_requested", "next_attempt_at", "created_at", "id"]


def upgrade() -> None:
    bind = op.get_bind()
    index_names = {index["name"] for index in inspect(bind).get_indexes("upload_tasks")}
    if INDEX_NAME not in index_names:
        op.create_index(INDEX_NAME, "upload_tasks", INDEX_COLUMNS, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    index_names = {index["name"] for index in inspect(bind).get_indexes("upload_tasks")}
    if INDEX_NAME in index_names:
        op.drop_index(INDEX_NAME, table_name="upload_tasks")
