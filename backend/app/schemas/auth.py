from pydantic import BaseModel, Field

from app.schemas.common import ImageSummary


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str = ""
    token_type: str = "cookie"
    expires_in: int
    username: str
    nickname: str
    avatar_image_id: int | None = None
    avatar_image: ImageSummary | None = None
    password_change_required: bool = False


class AuthUser(BaseModel):
    username: str
    nickname: str
    avatar_image_id: int | None = None
    avatar_image: ImageSummary | None = None
    password_change_required: bool = False
