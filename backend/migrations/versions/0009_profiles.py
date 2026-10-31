"""画像版本、覆盖记录和后台生成任务。"""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_versions", sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("data", sa.JSON(), nullable=False), sa.Column("covered_item_ids", sa.JSON(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False), sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
    )
    op.create_table(
        "profile_jobs", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(), nullable=False), sa.Column("stage", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False), sa.Column("batch_item_ids", sa.JSON(), nullable=False),
        sa.Column("covered_item_ids", sa.JSON(), nullable=False), sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("message_id", sa.String(), nullable=True), sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True), sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("profile_jobs")
    op.drop_table("profile_versions")
