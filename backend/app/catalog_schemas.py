from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

MediaType = Literal["movie", "tv", "season"]
SearchType = Literal["all", "movie", "tv"]


class CatalogRef(BaseModel):
    media_type: MediaType
    tmdb_id: int = Field(gt=0)
    season_number: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_season(self) -> Self:
        if (self.media_type == "season") != (self.season_number is not None):
            raise ValueError("单季作品必须指定季号；电影和整剧不填写季号。")
        return self

    @property
    def identity_key(self) -> str:
        key = f"{self.media_type}:{self.tmdb_id}"
        return key if self.season_number is None else f"{key}:{self.season_number}"


class Person(BaseModel):
    id: int | None = None
    name: str


class Genre(BaseModel):
    id: int | None = None
    name: str


class Country(BaseModel):
    iso_3166_1: str | None = None
    name: str


class Season(BaseModel):
    season_number: int
    name: str
    year: int | None
    episode_count: int
    poster_url: str | None


class CatalogCandidate(CatalogRef):
    title: str
    original_title: str
    year: int | None
    overview: str = ""
    poster_url: str | None


class SearchResult(BaseModel):
    items: list[CatalogCandidate]
    page: int
    total_pages: int


class CatalogDetail(CatalogCandidate):
    catalog_id: int
    confirmed: bool
    fetched_at: int
    overview_language: str | None
    original_language: str
    poster_path: str | None
    runtime: int | None
    genres: list[Genre]
    countries: list[Country]
    directors: list[Person]
    creators: list[Person]
    cast: list[Person]
    seasons: list[Season]
    tmdb_url: str
    alternative_titles: list[str]
    episode_count: int | None


class SourceReference(BaseModel):
    source: Literal["douban"] = "douban"
    source_id: str = Field(min_length=1)
    source_url: str | None = None


class ConfirmRequest(CatalogRef):
    source: SourceReference | None = None


class MatchRequest(BaseModel):
    title: str = Field(min_length=1)
    original_title: str | None = None
    year: int | None = None
    media_type: Literal["all", "movie", "tv", "season"] = "all"
    season_number: int | None = Field(default=None, ge=0)
    source: SourceReference | None = None


class MatchResult(BaseModel):
    status: Literal["matched", "ambiguous", "missing_data", "not_found"]
    reason: str
    item: CatalogDetail | None = None
    candidates: list[CatalogCandidate] = Field(default_factory=list)


class CatalogPage(BaseModel):
    items: list[CatalogDetail]
    total: int
    page: int
