from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ImageSummary, OrmModel, PageResponse


class WorkBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    original_name: str | None = None
    aliases: str | None = None
    description: str | None = None
    cover_image_id: int | None = None
    backdrop_image_id: int | None = None
    tagline: str | None = None
    production_year: int | None = None
    run_time_minutes: int | None = None
    community_rating: float | None = None
    content_rating: str | None = None
    genres: str | None = None
    studios: str | None = None
    official_site: str | None = None
    status: str | None = None
    sort_order: int = 0


class WorkCreate(WorkBase):
    pass


class WorkUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    original_name: str | None = None
    aliases: str | None = None
    description: str | None = None
    cover_image_id: int | None = None
    backdrop_image_id: int | None = None
    tagline: str | None = None
    production_year: int | None = None
    run_time_minutes: int | None = None
    community_rating: float | None = None
    content_rating: str | None = None
    genres: str | None = None
    studios: str | None = None
    official_site: str | None = None
    status: str | None = None
    sort_order: int | None = None


class WorkRead(WorkBase, OrmModel):
    id: int
    created_at: datetime
    updated_at: datetime
    cover_image: ImageSummary | None = None
    backdrop_image: ImageSummary | None = None


class WorkDetail(WorkRead):
    character_count: int = Field(default=0, ge=0)
    image_count: int = Field(default=0, ge=0)


class WorkListResponse(PageResponse[WorkRead]):
    pass
