from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin


class UploadTask(Base, TimestampMixin):
    __tablename__ = "upload_tasks"
    __table_args__ = (
        Index(
            "ix_upload_tasks_claim_ready",
            "status",
            "cancel_requested",
            "next_attempt_at",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False, index=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    staged_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    inspection_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    preflight_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating: Mapped[str] = mapped_column(String(20), default="safe", nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    artist_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_ids_csv: Mapped[str | None] = mapped_column(Text, nullable=True)
    character_ids_csv: Mapped[str | None] = mapped_column(Text, nullable=True)
    merge_duplicate_relations: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="SET NULL"), nullable=True, index=True)
    duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    staged_file_deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    image = relationship("Image", lazy="selectin")

    @property
    def staged_file_available(self) -> bool:
        return bool(self.staged_path and not self.staged_file_deleted_at)
