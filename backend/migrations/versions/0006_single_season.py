"""单正式季作品使用剧名和无季号识别键，保留个人记录。"""

from alembic import op
import sqlalchemy as sa

from app.catalog_service import name_year_key, season_presentation

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    works = sa.table("catalog_items", sa.column("id", sa.Integer), sa.column("media_type", sa.String),
                     sa.column("tmdb_id", sa.Integer), sa.column("season_number", sa.Integer),
                     sa.column("title", sa.String), sa.column("original_title", sa.String),
                     sa.column("year", sa.Integer), sa.column("details", sa.JSON), sa.column("match_key", sa.String))
    parents = {row.tmdb_id: row.details for row in connection.execute(sa.select(works).where(works.c.media_type == "tv"))}
    for row in connection.execute(sa.select(works).where(works.c.media_type == "season")).all():
        parent = parents.get(row.tmdb_id)
        if parent is None:
            continue
        season = next(s for s in parent["seasons"] if s["season_number"] == row.season_number)
        presentation = season_presentation(parent, row.season_number, season["name"])
        key = name_year_key(presentation["original_title"], presentation["title"], row.year,
                            None if presentation["single_season"] else row.season_number)
        connection.execute(works.update().where(works.c.id == row.id).values(
            title=presentation["title"], original_title=presentation["original_title"], match_key=key,
            details={**row.details, **presentation},
        ))


def downgrade() -> None:
    # 展示名称与识别键不影响 0005 的表结构，无需改动个人记录。
    pass
