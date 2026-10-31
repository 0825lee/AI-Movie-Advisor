from typing import Any

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProfileVersion(Base):
    __tablename__ = "profile_versions"

    version: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    covered_item_ids: Mapped[list[int]] = mapped_column(JSON)
    conversation_id: Mapped[str] = mapped_column(String)
    message_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[int] = mapped_column(Integer)


class ProfileJob(Base):
    __tablename__ = "profile_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String)
    stage: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer)
    batch_item_ids: Mapped[list[int]] = mapped_column(JSON)
    covered_item_ids: Mapped[list[int]] = mapped_column(JSON)
    conversation_id: Mapped[str | None] = mapped_column(String)
    message_id: Mapped[str | None] = mapped_column(String)
    task_id: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[int] = mapped_column(Integer)
