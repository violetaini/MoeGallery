from datetime import datetime

from pydantic import BaseModel

from app.schemas.image import ImageRead


class UploadTaskRead(BaseModel):
    id: int
    status: str
    original_filename: str | None = None
    file_size: int
    image_id: int | None = None
    duplicate: bool
    error_message: str | None = None
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


class UploadDuplicateCheckRequestItem(BaseModel):
    filename: str | None = None
    sha256: str


class UploadDuplicateCheckRequest(BaseModel):
    items: list[UploadDuplicateCheckRequestItem]


class UploadDuplicateCheckItem(BaseModel):
    filename: str | None = None
    sha256: str
    duplicate: bool
    duplicate_in_batch: bool
    existing_image: ImageRead | None = None


class UploadDuplicateCheckResponse(BaseModel):
    items: list[UploadDuplicateCheckItem]
