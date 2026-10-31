from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CatalogItem(Base):
    __tablename__ = "catalog_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    identity_key: Mapped[str] = mapped_column(String, unique=True)
    media_type: Mapped[str] = mapped_column(String)
    tmdb_id: Mapped[int | None] = mapped_column(Integer)
    match_key: Mapped[str | None] = mapped_column(String, index=True)
    season_number: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String)
    original_title: Mapped[str] = mapped_column(String)
    year: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    fetched_at: Mapped[int] = mapped_column(Integer)
    confirmed_at: Mapped[int | None] = mapped_column(Integer)


class SourceMapping(Base):
    __tablename__ = "source_mappings"
    __table_args__ = (UniqueConstraint("source", "source_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String)
    source_id: Mapped[str] = mapped_column(String)
    source_url: Mapped[str | None] = mapped_column(String)
    catalog_item_id: Mapped[int] = mapped_column(ForeignKey("catalog_items.id"))
