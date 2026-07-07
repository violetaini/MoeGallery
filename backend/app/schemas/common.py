from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ImageSummary(OrmModel):
    id: int
    filename: str
    file_path: str | None = None
    thumbnail_path: str | None = None
    preview_path: str | None = None
    mime_type: str | None = None
    width: int
    height: int
    orientation: str
    rating: str
    favorite_count: int
    dynamic_range: str
    is_animated: bool
    created_at: datetime


class WorkSummary(OrmModel):
    id: int
    name: str
    original_name: str | None = None
    cover_image_id: int | None = None
    sort_order: int = 0


class CharacterSummary(OrmModel):
    id: int
    work_id: int
    name: str
    original_name: str | None = None
    avatar_image_id: int | None = None


class TagSummary(OrmModel):
    id: int
    name: str
    type: str


T = TypeVar("T")


class PageResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
