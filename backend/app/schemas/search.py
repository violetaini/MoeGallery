from pydantic import BaseModel

from app.schemas.character import CharacterRead
from app.schemas.common import ImageSummary
from app.schemas.tag import TagRead
from app.schemas.work import WorkRead


class SearchResponse(BaseModel):
    images: list[ImageSummary]
    works: list[WorkRead]
    characters: list[CharacterRead]
    tags: list[TagRead]


class StatsResponse(BaseModel):
    image_count: int
    public_image_count: int
    work_count: int
    character_count: int
    total_file_size: int
