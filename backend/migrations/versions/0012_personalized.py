"""独立画像推荐模式及任务画像快照。"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recommendation_tasks", sa.Column("mode", sa.String(), nullable=False, server_default="request"))
    op.add_column("recommendation_tasks", sa.Column("profile_version", sa.Integer(), nullable=True))
    op.add_column("recommendation_tasks", sa.Column("profile_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recommendation_tasks") as batch:
        batch.drop_column("profile_snapshot")
        batch.drop_column("profile_version")
        batch.drop_column("mode")
