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
