from datetime import datetime

from pydantic import BaseModel, Field


class CdnWarmConfigUpdate(BaseModel):
    enabled: bool = False
    base_url: str = Field(default="", max_length=500)
    auto_new_uploads: bool = True


class CdnWarmConfigRead(CdnWarmConfigUpdate):
    valid: bool = False
    validation_message: str = ""


class CdnWarmProbeRead(BaseModel):
    base_url: str
    provider: str
    cache_status: str
    response_status: int | None = None
    detected: bool
    message: str
    error_code: str | None = None
    error_message: str | None = None


class CdnWarmTaskRead(BaseModel):
    id: int
    image_id: int
    variant: str
    media_version: int
    status: str
    provider: str
    cache_status: str = ""
    response_status: int | None = None
    response_bytes: int = 0
    attempt_count: int = 0
    error_code: str = ""
    error_message: str = ""
    updated_at: datetime


class CdnWarmStatusRead(BaseModel):
    config: CdnWarmConfigRead
    queued: int = 0
    processing: int = 0
    retry_wait: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    worker_alive: bool = False
    coverage_total: int = 0
    coverage_fresh: int = 0
    coverage_percentage: float = 0
    rewarm_after_seconds: int = 0
    recent_tasks: list[CdnWarmTaskRead] = Field(default_factory=list)


class CdnWarmSeedResult(BaseModel):
    queued: int = 0
    existing: int = 0
    retried: int = 0
    skipped: int = 0
