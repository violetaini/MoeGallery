from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import CharacterSummary, OrmModel, PageResponse, WorkSummary


class ShareCreate(BaseModel):
    image_ids: list[int] = Field(min_length=1, max_length=100)
    title: str | None = Field(default=None, max_length=255)
    expires_in_hours: int | None = Field(default=None, ge=1, le=8_760)

    @field_validator("image_ids")
    @classmethod
    def deduplicate_image_ids(cls, value: list[int]) -> list[int]:
        result = list(dict.fromkeys(value))
        if not result:
            raise ValueError("至少选择一张图片")
        return result

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ShareUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    expires_in_hours: int | None = Field(default=None, ge=1, le=8_760)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ShareImage(OrmModel):
    id: int
    filename: str
    original_filename: str | None = None
    media_version: int = 1
    mime_type: str | None = None
    width: int
    height: int
    orientation: str
    rating: str
    favorite_count: int
    dynamic_range: str
    is_animated: bool
    created_at: datetime
    artist_name: str | None = None


class ShareImageDetail(ShareImage):
    """Image metadata exposed only through its active share link."""

    file_size: int
    bit_depth: int
    color_profile: str | None = None
    source_url: str | None = None
    view_count: int
    works: list[WorkSummary] = []
    characters: list[CharacterSummary] = []


class ShareRead(OrmModel):
    id: int
    token: str
    title: str
    description: str | None = None
    is_active: bool
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    images: list[ShareImage] = []


class ShareListResponse(PageResponse[ShareRead]):
    pass


class SharePublicRead(BaseModel):
    token: str
    title: str
    image_count: int = Field(ge=1)
    images: list[ShareImage]
