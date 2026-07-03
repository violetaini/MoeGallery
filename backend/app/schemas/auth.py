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
    avatar_image_id: int | None = None
    avatar_image: ImageSummary | None = None


class AuthUser(BaseModel):
    username: str
    avatar_image_id: int | None = None
    avatar_image: ImageSummary | None = None
