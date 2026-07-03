from pydantic import BaseModel, Field


class MetadataImportRow(BaseModel):
    row_number: int
    action: str
    status: str
    work_name: str | None = None
    character_name: str | None = None
    message: str = ""


class MetadataImportSummary(BaseModel):
    dry_run: bool
    total_rows: int
    valid_rows: int
    error_rows: int
    works_created: int = 0
    works_updated: int = 0
    characters_created: int = 0
    characters_updated: int = 0
    rows: list[MetadataImportRow] = Field(default_factory=list)

