from datetime import UTC, datetime


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
