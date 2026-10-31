from typing import Any

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProfileRecord(Base):
    __tablename__ = "profile_records"

    user_item_id: Mapped[int] = mapped_column(ForeignKey("user_items.id", ondelete="CASCADE"), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
