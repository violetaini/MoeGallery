from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.image import ImageRead


class UploadTaskRead(BaseModel):
    id: int
    status: str
    original_filename: str | None = None
    file_size: int
    sha256: str | None = None
    preflight_duplicate: bool = False
    image_id: int | None = None
    duplicate: bool
    attempt_count: int = 0
    max_attempts: int = 3
    next_attempt_at: datetime | None = None
    worker_id: str | None = None
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    cancel_requested: bool = False
    error_code: str | None = None
    error_message: str | None = None
    staged_file_available: bool = False
    staged_file_deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    image: ImageRead | None = None

    model_config = {"from_attributes": True}


class UploadTaskCreateResponse(BaseModel):
    items: list[UploadTaskRead]


class UploadTaskListResponse(BaseModel):
    items: list[UploadTaskRead]
    total: int
    page: int
    page_size: int


class UploadTaskBatchActionRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)
    action: Literal["retry", "cancel", "delete"]


class UploadTaskBatchActionResponse(BaseModel):
    affected: int
    skipped: int


class UploadDuplicateCheckRequestItem(BaseModel):
    filename: str | None = None
    sha256: str = Field(pattern="^[0-9a-fA-F]{64}$")


class UploadDuplicateCheckRequest(BaseModel):
    items: list[UploadDuplicateCheckRequestItem] = Field(min_length=1, max_length=5000)


class UploadDuplicateCheckItem(BaseModel):
    filename: str | None = None
    sha256: str
    duplicate: bool
    duplicate_in_queue: bool = False
    duplicate_in_batch: bool
    existing_image: ImageRead | None = None


class UploadDuplicateCheckResponse(BaseModel):
    items: list[UploadDuplicateCheckItem]
