"""豆瓣作品无需 TMDB ID，按原名和年份识别个人记录。"""

from alembic import op
import sqlalchemy as sa

from app.catalog_service import name_year_key

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite 重建被外键引用的资料表时，暂时关闭外键；原 ID 和引用保持不变。
    with op.get_context().autocommit_block():
        op.execute("PRAGMA foreign_keys=OFF")
        with op.batch_alter_table("catalog_items") as batch:
            batch.alter_column("tmdb_id", existing_type=sa.Integer(), nullable=True)
            batch.add_column(sa.Column("match_key", sa.String(), nullable=True))
            batch.create_index("ix_catalog_items_match_key", ["match_key"])
        op.execute("PRAGMA foreign_keys=ON")
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, original_title, title, year, season_number FROM catalog_items")).mappings().all()
    for row in rows:
        key = name_year_key(row["original_title"], row["title"], row["year"], row["season_number"])
        connection.execute(sa.text("UPDATE catalog_items SET match_key=:key WHERE id=:id"), {"key": key, "id": row["id"]})


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM catalog_items WHERE tmdb_id IS NULL")):
        raise ValueError("存在没有 TMDB ID 的豆瓣资料，不能回退到强制 TMDB 的版本。")
    with op.get_context().autocommit_block():
        op.execute("PRAGMA foreign_keys=OFF")
        with op.batch_alter_table("catalog_items") as batch:
            batch.drop_index("ix_catalog_items_match_key")
            batch.drop_column("match_key")
            batch.alter_column("tmdb_id", existing_type=sa.Integer(), nullable=False)
        op.execute("PRAGMA foreign_keys=ON")
