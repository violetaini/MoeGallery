from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ImageSummary, OrmModel, PageResponse


class TagBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(default="general", pattern="^(general|artist|style|clothing|scene|meta)$")
    aliases: str | None = None


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    type: str | None = Field(default=None, pattern="^(general|artist|style|clothing|scene|meta)$")
    aliases: str | None = None


class TagRead(TagBase, OrmModel):
    id: int
    created_at: datetime
    updated_at: datetime


class TagDetail(TagRead):
    images: list[ImageSummary] = []


class TagListResponse(PageResponse[TagRead]):
    pass

