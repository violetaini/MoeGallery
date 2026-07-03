from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.associations import image_works
from app.models.mixins import TimestampMixin


class Work(Base, TimestampMixin):
    __tablename__ = "works"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    aliases: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="SET NULL"), nullable=True)
    backdrop_image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="SET NULL"), nullable=True)
    tagline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    production_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    run_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    community_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    content_rating: Mapped[str | None] = mapped_column(String(80), nullable=True)
    genres: Mapped[str | None] = mapped_column(Text, nullable=True)
    studios: Mapped[str | None] = mapped_column(Text, nullable=True)
    official_site: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)

    cover_image = relationship("Image", foreign_keys=[cover_image_id], lazy="selectin")
    backdrop_image = relationship("Image", foreign_keys=[backdrop_image_id], lazy="selectin")
    characters = relationship("Character", back_populates="work", cascade="all, delete-orphan", passive_deletes=True)
    images = relationship("Image", secondary=image_works, back_populates="works", lazy="selectin")
