"""本次需求推荐批次、任务、候选及屏蔽基础。"""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_batches", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("request_text", sa.String(), nullable=False),
        sa.Column("shown_ids", sa.JSON(), nullable=False), sa.Column("created_at", sa.Integer(), nullable=False),
    )
    op.create_table(
        "recommendation_tasks", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("batch_id", sa.String(), sa.ForeignKey("recommendation_batches.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False), sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("criteria", sa.JSON(), nullable=True), sa.Column("filters", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True), sa.Column("workflow_run_id", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True), sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_recommendation_tasks_batch_id", "recommendation_tasks", ["batch_id"])
    op.create_table(
        "recommendation_candidates",
        sa.Column("task_id", sa.String(), sa.ForeignKey("recommendation_tasks.id"), primary_key=True),
        sa.Column("catalog_id", sa.Integer(), sa.ForeignKey("catalog_items.id"), primary_key=True),
        sa.Column("relaxation_stage", sa.Integer(), nullable=False),
    )
    op.create_table(
        "blocked_movies", sa.Column("catalog_id", sa.Integer(), sa.ForeignKey("catalog_items.id"), primary_key=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    for name in ["blocked_movies", "recommendation_candidates", "recommendation_tasks", "recommendation_batches"]:
        op.drop_table(name)
