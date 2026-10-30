from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserItem(Base):
    __tablename__ = "user_items"
    __table_args__ = (
        CheckConstraint("status IN ('wish', 'watched')", name="library_status"),
        CheckConstraint("rating IS NULL OR rating IN (1, 2, 3, 4, 5)", name="integer_stars"),
        CheckConstraint("status != 'wish' OR rating IS NULL", name="wish_without_rating"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    catalog_item_id: Mapped[int] = mapped_column(ForeignKey("catalog_items.id"), unique=True)
    status: Mapped[str] = mapped_column(String)
    rating: Mapped[int | None] = mapped_column(Integer)
    marked_at: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String)
    created_at: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[int] = mapped_column(Integer)
