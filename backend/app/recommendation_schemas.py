from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.catalog_schemas import CatalogDetail

CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
LanguageCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{2}$")]


class RequestCriteria(BaseModel):
    year_requirement: str = ""
    runtime_requirement: str = ""
    year_from: int | None = Field(default=None, ge=1800, le=9999)
    year_to: int | None = Field(default=None, ge=1800, le=9999)
    runtime_min: int | None = Field(default=None, ge=1)
    runtime_max: int | None = Field(default=None, ge=1)
    countries: list[CountryCode] = Field(default_factory=list)
    languages: list[LanguageCode] = Field(default_factory=list)
    preferred_genres: list[str] = Field(default_factory=list)
    excluded_genres: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    moods: list[str] = Field(default_factory=list)
    other_exclusions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ordered_ranges(self) -> Self:
        for low, high in [(self.year_from, self.year_to), (self.runtime_min, self.runtime_max)]:
            if low is not None and high is not None and low > high:
                raise ValueError("条件下限不能大于上限。")
        return self


class RecommendationRequest(BaseModel):
    request_text: str = Field(min_length=1)


class MovieSearchInput(BaseModel):
    task_id: str
    target_count: int = Field(default=3, ge=1, le=3)


class MovieDetailsInput(BaseModel):
    task_id: str
    movie_id: int = Field(gt=0, description="search_movies 返回的 movie_id（本地作品 ID），不是 TMDB ID。")


class RecommendationSelection(BaseModel):
    movie_ids: list[int]
    reasons: list[str]


class RecommendationCard(BaseModel):
    movie_id: int
    reason: str
    movie: CatalogDetail


class RecommendationState(BaseModel):
    task_id: str
    batch_id: str
    status: str
    request_text: str
    target_count: int
    criteria: RequestCriteria | None
    cards: list[RecommendationCard]
    needs_refresh: bool
    workflow_run_id: str | None
    error: str | None
    created_at: int
