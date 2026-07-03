from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import CharacterSummary, ImageSummary, OrmModel, PageResponse, TagSummary, WorkSummary


class ImageUpdate(BaseModel):
    original_filename: str | None = None
    rating: str | None = Field(default=None, pattern="^(safe|sensitive|hidden)$")
    source_url: str | None = None
    artist_name: str | None = None
    is_public: bool | None = None
    favorite_count: int | None = Field(default=None, ge=0)
    work_ids: list[int] | None = None
    character_ids: list[int] | None = None


class ImageBatchItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: str | None = Field(default=None, pattern="^(safe|sensitive|hidden)$")
    source_url: str | None = None
    artist_name: str | None = None
    favorite_count: int | None = Field(default=None, ge=0)
    work_ids: list[int] | None = None
    character_ids: list[int] | None = None


class ImageBatchUpdate(BaseModel):
    image_ids: list[int] = Field(min_length=1)
    update: ImageBatchItemUpdate


class ImageBatchDelete(BaseModel):
    image_ids: list[int] = Field(min_length=1)


class ImageBatchResult(BaseModel):
    count: int


class ImageRead(ImageSummary):
    original_filename: str | None = None
    file_path: str
    file_size: int
    mime_type: str
    bit_depth: int
    color_profile: str | None = None
    sha256: str
    phash: str | None = None
    source_url: str | None = None
    artist_name: str | None = None
    is_public: bool
    view_count: int
    updated_at: datetime
    works: list[WorkSummary] = []
    characters: list[CharacterSummary] = []
    tags: list[TagSummary] = []


class ImageUploadResult(OrmModel):
    image: ImageRead
    duplicate: bool = False


class ImageUploadResponse(BaseModel):
    items: list[ImageUploadResult]


class ImageListResponse(PageResponse[ImageRead]):
    pass
