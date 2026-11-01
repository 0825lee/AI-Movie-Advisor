from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RecommendationBatch(Base):
    __tablename__ = "recommendation_batches"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    request_text: Mapped[str] = mapped_column(String)
    shown_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    created_at: Mapped[int] = mapped_column(Integer)


class RecommendationTask(Base):
    __tablename__ = "recommendation_tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("recommendation_batches.id"), index=True)
    status: Mapped[str] = mapped_column(String)
    strategy: Mapped[str] = mapped_column(String, default="ai_nomination", server_default="criteria")
    mode: Mapped[str] = mapped_column(String, default="request", server_default="request")
    profile_version: Mapped[int | None] = mapped_column(Integer)
    profile_snapshot: Mapped[dict | None] = mapped_column(JSON)
    target_count: Mapped[int] = mapped_column(Integer)
    criteria: Mapped[dict | None] = mapped_column(JSON)
    filters: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[list[dict] | None] = mapped_column(JSON)
    workflow_run_id: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[int] = mapped_column(Integer)


class RecommendationCandidate(Base):
    __tablename__ = "recommendation_candidates"

    task_id: Mapped[str] = mapped_column(ForeignKey("recommendation_tasks.id"), primary_key=True)
    catalog_id: Mapped[int] = mapped_column(ForeignKey("catalog_items.id"), primary_key=True)
    relaxation_stage: Mapped[int] = mapped_column(Integer)


class BlockedMovie(Base):
    __tablename__ = "blocked_movies"

    catalog_id: Mapped[int] = mapped_column(ForeignKey("catalog_items.id"), primary_key=True)
    created_at: Mapped[int] = mapped_column(Integer)


class MovieVerification(Base):
    __tablename__ = "movie_verifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("recommendation_tasks.id"), index=True)
    proposal: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String)
    catalog_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_items.id"))
    reason: Mapped[str] = mapped_column(String)
    created_at: Mapped[int] = mapped_column(Integer)
