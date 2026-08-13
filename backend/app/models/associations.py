from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Table

from app.database import Base
from app.utils.time import utcnow_naive


image_works = Table(
    "image_works",
    Base.metadata,
    Column("image_id", ForeignKey("images.id", ondelete="CASCADE"), primary_key=True),
    Column("work_id", ForeignKey("works.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime, default=utcnow_naive, nullable=False),
    Index("ix_image_works_work_image", "work_id", "image_id"),
)

image_characters = Table(
    "image_characters",
    Base.metadata,
    Column("image_id", ForeignKey("images.id", ondelete="CASCADE"), primary_key=True),
    Column("character_id", ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime, default=utcnow_naive, nullable=False),
    Index("ix_image_characters_character_image", "character_id", "image_id"),
)

image_tags = Table(
    "image_tags",
    Base.metadata,
    Column("image_id", ForeignKey("images.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime, default=utcnow_naive, nullable=False),
    Index("ix_image_tags_tag_image", "tag_id", "image_id"),
)
