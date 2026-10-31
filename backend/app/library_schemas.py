from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.catalog_schemas import CatalogRef, Country, Genre, Person

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


class LibraryWork(BaseModel):
    catalog_id: int
    media_type: str
    tmdb_id: int | None
    season_number: int | None = None
    title: str
    original_title: str
    year: int | None
    overview: str = ""
    overview_language: str | None = None
    original_language: str = ""
    poster_url: str | None = None
    runtime: int | None = None
    genres: list[Genre] = Field(default_factory=list)
    countries: list[Country] = Field(default_factory=list)
    directors: list[Person] = Field(default_factory=list)
    creators: list[Person] = Field(default_factory=list)
    cast: list[Person] = Field(default_factory=list)
    seasons: list[dict] = Field(default_factory=list)
    episode_count: int | None = None
    tmdb_url: str | None = None
    source_url: str
    source_name: str
    info: str = ""
    languages: list[str] = Field(default_factory=list)


class LibraryEntry(BaseModel):
    id: int
    status: LibraryStatus
    rating: int | None
    score: int | None
    marked_at: int | None
    source: str
    catalog: LibraryWork


class LibraryCounts(BaseModel):
    wish: int = 0
    watched: int = 0


class ClearLibraryResult(BaseModel):
    deleted: int


class LibraryPage(BaseModel):
    items: list[LibraryEntry]
    counts: LibraryCounts
    total: int
    page: int
    page_size: int = 12
