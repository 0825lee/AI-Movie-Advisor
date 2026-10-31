from pydantic import BaseModel


class ProfileEvidence(BaseModel):
    title: str
    originalTitle: str
    rating: int | None
    commentExcerpt: str | None


class ProfileConclusion(BaseModel):
    dimension: str
    label: str
    reason: str
    evidence: list[ProfileEvidence]


class TasteProfile(BaseModel):
    version: int
    covered_count: int
    summary: str
    preferences: list[ProfileConclusion]
    less_preferred: list[ProfileConclusion]
    recent_changes: list[ProfileConclusion]
    limitations: list[str]


class ProfileJobState(BaseModel):
    id: int
    status: str
    stage: str
    version: int
    batch_count: int
    error: str | None
    created_at: int


class ProfileState(BaseModel):
    profile: TasteProfile | None
    created_at: int | None
    watched_count: int
    covered_count: int
    pending_count: int
    remaining: int
    configured: bool
    generating: bool
    job: ProfileJobState | None
