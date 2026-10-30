"""导入任务、逐条结果及可缺失的原始标记日期。"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_items") as batch:
        batch.alter_column("marked_at", existing_type=sa.Integer(), nullable=True)
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )
    op.create_table(
        "import_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("catalog_item_id", sa.Integer(), sa.ForeignKey("catalog_items.id"), nullable=True),
        sa.UniqueConstraint("job_id", "row_number"),
    )
    op.create_index("ix_import_rows_job_id", "import_rows", ["job_id"])


def downgrade() -> None:
    op.drop_table("import_rows")
    op.drop_table("import_jobs")
    # 回退前以创建时间填补没有原始标记日期的记录。
    op.execute("UPDATE user_items SET marked_at = created_at WHERE marked_at IS NULL")
    with op.batch_alter_table("user_items") as batch:
        batch.alter_column("marked_at", existing_type=sa.Integer(), nullable=False)
