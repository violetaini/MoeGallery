from pydantic import BaseModel, Field, model_validator


class InstallStatus(BaseModel):
    installed: bool
    lock_exists: bool
    database_initialized: bool
    restart_required: bool = False


class InstallRequest(BaseModel):
    database_type: str = Field(pattern="^(sqlite|mysql)$")
    sqlite_path: str | None = None
    mysql_host: str | None = None
    mysql_port: int = Field(default=3306, ge=1, le=65535)
    mysql_database: str | None = None
    mysql_username: str | None = None
    mysql_password: str | None = None
    admin_username: str = Field(min_length=1, max_length=80)
    admin_password: str = Field(min_length=6, max_length=128)
    auth_secret: str | None = Field(default=None, min_length=32, max_length=256)

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
        return self


class InstallResponse(BaseModel):
    installed: bool
    database_type: str
    restart_required: bool
