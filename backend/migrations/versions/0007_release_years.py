"""从原始 info 补全上映年份与去重键，保留展示年份和个人记录。"""

from alembic import op
import sqlalchemy as sa

from app.catalog_service import work_match_keys
from app.douban_metadata import release_years

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    works = sa.table("catalog_items", sa.column("id", sa.Integer), sa.column("title", sa.String),
                     sa.column("original_title", sa.String), sa.column("year", sa.Integer),
                     sa.column("season_number", sa.Integer), sa.column("details", sa.JSON))
    for row in connection.execute(sa.select(works)).all():
        data = {**row.details, "title": row.title, "original_title": row.original_title,
                "year": row.year, "season_number": row.season_number}
        data["release_years"] = release_years(data.get("info") or "", row.year)
        data["match_keys"] = work_match_keys(data)
        connection.execute(works.update().where(works.c.id == row.id).values(details=data))


def downgrade() -> None:
    # 0006 忽略这些扩展资料，个人记录与显示年份均不需要改动。
    pass
