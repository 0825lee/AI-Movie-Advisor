from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.catalog_schemas import CatalogDetail, CatalogRef

LibraryStatus = Literal["wish", "watched"]
Stars = Annotated[int, Field(strict=True, ge=1, le=5)]


class ManualAdd(CatalogRef):
    status: LibraryStatus
    rating: Stars | None = None

    @model_validator(mode="after")
    def check_entry(self) -> Self:
        if self.media_type == "tv":
            raise ValueError("剧集请按季标记，选择具体季的搜索结果。")
        if self.status == "wish" and self.rating is not None:
            raise ValueError("想看记录不填写评分。")
        return self


class MarkWatched(BaseModel):
    rating: Stars | None = None


class LibraryState(BaseModel):
    item_id: int | None = None
    status: LibraryStatus | None = None
    rating: int | None = None
    score: int | None = None


class LibraryEntry(BaseModel):
    id: int
    status: LibraryStatus
    rating: int | None
    score: int | None
    marked_at: int
    source: str
    catalog: CatalogDetail


class LibraryCounts(BaseModel):
    wish: int = 0
    watched: int = 0


class LibraryPage(BaseModel):
    items: list[LibraryEntry]
    counts: LibraryCounts
    total: int
    page: int
    page_size: int = 12
