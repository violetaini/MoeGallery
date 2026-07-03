from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.associations import image_characters, image_tags, image_works
from app.models.mixins import TimestampMixin


class Image(Base, TimestampMixin):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preview_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    width: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    is_animated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    dynamic_range: Mapped[str] = mapped_column(String(20), default="sdr", nullable=False, index=True)
    bit_depth: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    color_profile: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    phash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    rating: Mapped[str] = mapped_column(String(20), default="safe", nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    artist_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    favorite_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    works = relationship("Work", secondary=image_works, back_populates="images", lazy="selectin")
    characters = relationship("Character", secondary=image_characters, back_populates="images", lazy="selectin")
    tags = relationship("Tag", secondary=image_tags, back_populates="images", lazy="selectin")
