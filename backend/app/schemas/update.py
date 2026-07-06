from datetime import datetime

from pydantic import BaseModel, Field


class ReleaseAsset(BaseModel):
    name: str
    size: int = 0
    browser_download_url: str


class LatestRelease(BaseModel):
    available: bool
    version: str = ""
    url: str = ""
    assets: list[ReleaseAsset] = Field(default_factory=list)
    proxied: bool = False
    checked_at: int = 0
    message: str = ""


class UpdateCheckResponse(BaseModel):
    current_version: str
    latest_release: LatestRelease
    update_available: bool
    updater_available: bool
    updater_mode: str
    updater_status: dict = Field(default_factory=dict)


class UpdateTaskCreate(BaseModel):
    version: str | None = None
    dry_run: bool = False
    force: bool = False


class UpdateTaskRead(BaseModel):
    id: str
    status: str
    current_version: str
    target_version: str
    release_url: str = ""
    archive_url: str = ""
    checksum_url: str = ""
    archive_name: str = ""
    dry_run: bool = False
    progress: int = 0
    message: str = ""
    log: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class UpdateTaskListResponse(BaseModel):
    items: list[UpdateTaskRead] = Field(default_factory=list)
