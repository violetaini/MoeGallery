from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ImageSummary, OrmModel, PageResponse, WorkSummary


class CharacterBase(BaseModel):
    work_id: int
    name: str = Field(min_length=1, max_length=255)
    original_name: str | None = None
    aliases: str | None = None
    description: str | None = None
    avatar_image_id: int | None = None


class CharacterCreate(CharacterBase):
    pass


class CharacterUpdate(BaseModel):
    work_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    original_name: str | None = None
    aliases: str | None = None
    description: str | None = None
    avatar_image_id: int | None = None


class CharacterRead(CharacterBase, OrmModel):
    id: int
    created_at: datetime
    updated_at: datetime
    work: WorkSummary | None = None
    avatar_image: ImageSummary | None = None


class CharacterDetail(CharacterRead):
    images: list[ImageSummary] = []


class CharacterListResponse(PageResponse[CharacterRead]):
    pass

