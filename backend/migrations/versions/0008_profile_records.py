"""按个人片库记录保存六字段画像输入，清库时级联删除。"""

from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa

from app.profile_records import manual_info

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = op.create_table(
        "profile_records",
        sa.Column("user_item_id", sa.Integer(), sa.ForeignKey("user_items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    connection = op.get_bind()
    works = sa.table("catalog_items", sa.column("id", sa.Integer), sa.column("title", sa.String),
                     sa.column("original_title", sa.String), sa.column("details", sa.JSON))
    items = sa.table("user_items", sa.column("id", sa.Integer), sa.column("catalog_item_id", sa.Integer),
                     sa.column("rating", sa.Integer), sa.column("marked_at", sa.Integer))
    rows = connection.execute(sa.select(items.c.id, items.c.rating, items.c.marked_at,
                                       works.c.title, works.c.original_title, works.c.details).join_from(
                                           items, works, items.c.catalog_item_id == works.c.id)).all()
    for row in rows:
        payload = dict(title=row.title, originalTitle=row.original_title, info=manual_info(row.details),
                       rating=row.rating * 2 if row.rating is not None else None,
                       markedAt=datetime.fromtimestamp(row.marked_at, timezone(timedelta(hours=8))).date().isoformat() if row.marked_at is not None else "",
                       comment="")
        connection.execute(table.insert().values(user_item_id=row.id, payload=payload))


def downgrade() -> None:
    op.drop_table("profile_records")
