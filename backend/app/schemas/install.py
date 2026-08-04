from pydantic import BaseModel, Field, model_validator


class InstallStatus(BaseModel):
    installed: bool
    restart_required: bool = False
    token_required: bool = False


class InstallRequest(BaseModel):
    database_type: str = Field(pattern="^(sqlite|mysql)$")
    sqlite_path: str | None = None
    mysql_host: str | None = None
    mysql_port: int = Field(default=3306, ge=1, le=65535)
    mysql_database: str | None = None
    mysql_username: str | None = None
    mysql_password: str | None = None
    admin_username: str = Field(min_length=1, max_length=80)
    admin_password: str = Field(min_length=12, max_length=128)

    @model_validator(mode="after")
    def validate_database_fields(self):
        if self.database_type == "mysql":
            missing = [
                field
                for field in ("mysql_host", "mysql_database", "mysql_username", "mysql_password")
                if not getattr(self, field)
            ]
            if missing:
                raise ValueError(f"Missing MySQL fields: {', '.join(missing)}")
        normalized_password = self.admin_password.strip().casefold()
        normalized_username = self.admin_username.strip().casefold()
        if self.admin_password != self.admin_password.strip():
            raise ValueError("管理员密码首尾不能包含空格")
        if normalized_password == normalized_username:
            raise ValueError("管理员密码不能与用户名相同")
        if normalized_password in {"admin123", "password", "password123", "change-this-password"}:
            raise ValueError("管理员密码过于简单")
        return self


class InstallResponse(BaseModel):
    installed: bool
    database_type: str
    restart_required: bool
