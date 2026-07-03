from pydantic import BaseModel, Field

from app.schemas.common import ImageSummary


class AdminSettingsRead(BaseModel):
    image_manage_view_mode: str = Field(default="classic", pattern="^(classic|waterfall)$")
    upload_worker_count: int = Field(default=12, ge=1, le=96)
    upload_claim_batch_size: int = Field(default=1, ge=1, le=100)
    admin_username: str
    admin_avatar_image_id: int | None = None
    admin_avatar_image: ImageSummary | None = None
    home_slideshow_image_ids: list[int] = Field(default_factory=list)
    home_slideshow_images: list[ImageSummary] = Field(default_factory=list)
    home_hero_image_id: int | None = None
    home_hero_image: ImageSummary | None = None
    works_hero_image_id: int | None = None
    works_hero_image: ImageSummary | None = None
    characters_hero_image_id: int | None = None
    characters_hero_image: ImageSummary | None = None
    ratings_hero_image_id: int | None = None
    ratings_hero_image: ImageSummary | None = None


class AdminSettingsUpdate(BaseModel):
    image_manage_view_mode: str | None = Field(default=None, pattern="^(classic|waterfall)$")
    upload_worker_count: int | None = Field(default=None, ge=1, le=96)
    upload_claim_batch_size: int | None = Field(default=None, ge=1, le=100)
    admin_username: str | None = Field(default=None, min_length=1, max_length=80)
    admin_password: str | None = Field(default=None, min_length=6, max_length=128)
    admin_avatar_image_id: int | None = Field(default=None, ge=1)
    clear_admin_avatar: bool | None = None
    home_slideshow_image_ids: list[int] | None = Field(default=None, max_length=24)
    home_hero_image_id: int | None = Field(default=None, ge=1)
    clear_home_hero_image: bool | None = None
    works_hero_image_id: int | None = Field(default=None, ge=1)
    clear_works_hero_image: bool | None = None
    characters_hero_image_id: int | None = Field(default=None, ge=1)
    clear_characters_hero_image: bool | None = None
    ratings_hero_image_id: int | None = Field(default=None, ge=1)
    clear_ratings_hero_image: bool | None = None


class PublicSettingsRead(BaseModel):
    home_slideshow_image_ids: list[int] = Field(default_factory=list)
    home_slideshow_images: list[ImageSummary] = Field(default_factory=list)
    home_hero_image_id: int | None = None
    home_hero_image: ImageSummary | None = None
    works_hero_image_id: int | None = None
    works_hero_image: ImageSummary | None = None
    characters_hero_image_id: int | None = None
    characters_hero_image: ImageSummary | None = None
    ratings_hero_image_id: int | None = None
    ratings_hero_image: ImageSummary | None = None
