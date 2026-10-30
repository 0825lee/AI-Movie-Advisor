from typing import Any, Literal

from pydantic import BaseModel

ImportStatus = Literal["running", "paused", "completed", "cancelled"]
ImportOutcome = Literal["pending", "added", "upgraded", "duplicate", "skipped", "failed"]


class ImportRequest(BaseModel):
    filename: str
    data: dict[str, Any]


class ImportCounts(BaseModel):
    added: int = 0
    upgraded: int = 0
    duplicate: int = 0
    skipped: int = 0
    failed: int = 0


class ImportSummary(BaseModel):
    id: int
    filename: str
    status: ImportStatus
    total: int
    processed: int
    counts: ImportCounts
    message: str | None
    current_title: str | None
    created_at: int


class ImportRowResult(BaseModel):
    row_number: int
    title: str
    outcome: ImportOutcome
    message: str | None
    matched_title: str | None


class ImportRowsPage(BaseModel):
    items: list[ImportRowResult]
    total: int
    page: int
    page_size: int = 20
