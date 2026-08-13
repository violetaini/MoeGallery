from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.utils.time import utcnow_naive


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
