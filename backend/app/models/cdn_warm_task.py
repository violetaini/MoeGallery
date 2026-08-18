from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class CdnWarmTask(Base, TimestampMixin):
    __tablename__ = "cdn_warm_tasks"
    __table_args__ = (
        UniqueConstraint("image_id", "variant", "media_version", name="uq_cdn_warm_tasks_image_variant_version"),
        Index("ix_cdn_warm_tasks_claim_ready", "status", "next_attempt_at", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"), nullable=False, index=True)
    variant: Mapped[str] = mapped_column(String(20), nullable=False)
    media_version: Mapped[int] = mapped_column(Integer, nullable=False)
    target_url: Mapped[str] = mapped_column(String(1200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    cache_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
