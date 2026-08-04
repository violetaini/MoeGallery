from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ImageSummary


class ApiKeyRead(BaseModel):
    id: int
    name: str
    key: str
    scopes: list[str]
    full_access: bool
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    last_used_ip: str | None = None
    status: str = Field(pattern="^(active|expired|revoked)$")


class ApiKeyScopeRead(BaseModel):
    value: str
    label: str
    description: str


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[str] = Field(min_length=1, max_length=9)
    expires_at: datetime | None = None


class ApiKeyUpdate(ApiKeyCreate):
    pass


class AdminSettingsRead(BaseModel):
    image_manage_view_mode: str = Field(default="classic", pattern="^(classic|waterfall)$")
    random_api_desktop_orientation: str = Field(default="landscape", pattern="^(landscape|portrait|square|any)$")
    random_api_mobile_orientation: str = Field(default="portrait", pattern="^(landscape|portrait|square|any)$")
    random_api_default_rating: str = Field(default="safe", pattern="^(safe|sensitive|any)$")
    random_api_default_variant: str = Field(default="preview", pattern="^(original|preview|thumbnail)$")
    upload_worker_count: int = Field(default=12, ge=1, le=96)
    upload_worker_limit: int = Field(default=96, ge=1, le=96)
    database_concurrency_profile: str = Field(default="generic", max_length=80)
    upload_claim_batch_size: int = Field(default=1, ge=1, le=100)
    upload_task_max_attempts: int = Field(default=3, ge=1, le=10)
    upload_failed_retention_days: int = Field(default=7, ge=1, le=90)
    github_proxy_url: str = Field(default="", max_length=500)
    admin_username: str
    admin_avatar_image_id: int | None = None
    admin_avatar_image: ImageSummary | None = None
    admin_password_change_required: bool = False
    operations_api_keys: list[ApiKeyRead] = Field(default_factory=list)
    api_key_scopes: list[ApiKeyScopeRead] = Field(default_factory=list)
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
    random_api_desktop_orientation: str | None = Field(default=None, pattern="^(landscape|portrait|square|any)$")
    random_api_mobile_orientation: str | None = Field(default=None, pattern="^(landscape|portrait|square|any)$")
    random_api_default_rating: str | None = Field(default=None, pattern="^(safe|sensitive|any)$")
    random_api_default_variant: str | None = Field(default=None, pattern="^(original|preview|thumbnail)$")
    upload_worker_count: int | None = Field(default=None, ge=1, le=96)
    upload_claim_batch_size: int | None = Field(default=None, ge=1, le=100)
    upload_task_max_attempts: int | None = Field(default=None, ge=1, le=10)
    upload_failed_retention_days: int | None = Field(default=None, ge=1, le=90)
    github_proxy_url: str | None = Field(default=None, max_length=500)
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
