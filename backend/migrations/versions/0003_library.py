"""个人想看、看过与可选整数星评分。"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("catalog_item_id", sa.Integer(), sa.ForeignKey("catalog_items.id"), nullable=False, unique=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("marked_at", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('wish', 'watched')", name="library_status"),
        sa.CheckConstraint("rating IS NULL OR rating IN (1, 2, 3, 4, 5)", name="integer_stars"),
        sa.CheckConstraint("status != 'wish' OR rating IS NULL", name="wish_without_rating"),
    )


def downgrade() -> None:
    op.drop_table("user_items")
