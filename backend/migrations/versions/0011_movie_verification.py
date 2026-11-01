"""Agent 提名策略及逐条核实记录，旧任务保持 criteria 标识。"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recommendation_tasks", sa.Column("strategy", sa.String(), nullable=False, server_default="criteria"))
    op.create_table(
        "movie_verifications", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("recommendation_tasks.id"), nullable=False),
        sa.Column("proposal", sa.JSON(), nullable=False), sa.Column("status", sa.String(), nullable=False),
        sa.Column("catalog_id", sa.Integer(), sa.ForeignKey("catalog_items.id"), nullable=True),
        sa.Column("reason", sa.String(), nullable=False), sa.Column("created_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_movie_verifications_task_id", "movie_verifications", ["task_id"])


def downgrade() -> None:
    op.drop_table("movie_verifications")
    with op.batch_alter_table("recommendation_tasks") as batch:
        batch.drop_column("strategy")
