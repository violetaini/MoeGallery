from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.associations import image_tags
from app.models.mixins import TimestampMixin


class Tag(Base, TimestampMixin):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(40), default="general", nullable=False, index=True)
    aliases: Mapped[str | None] = mapped_column(Text, nullable=True)

    images = relationship("Image", secondary=image_tags, back_populates="tags", lazy="selectin")

