from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.associations import image_characters
from app.models.mixins import TimestampMixin


class Character(Base, TimestampMixin):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    aliases: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="SET NULL"), nullable=True)

    work = relationship("Work", back_populates="characters", lazy="selectin")
    avatar_image = relationship("Image", foreign_keys=[avatar_image_id], lazy="selectin")
    images = relationship("Image", secondary=image_characters, back_populates="characters", lazy="selectin")

