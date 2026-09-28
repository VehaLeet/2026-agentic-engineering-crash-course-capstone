"""Create DAM prices, day hashes, and raw snapshots.

Revision ID: 0001_dam_storage
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_dam_storage"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dam_prices",
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("period", sa.SmallInteger(), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("volume_sell", sa.Numeric(12, 1), nullable=False),
        sa.Column("volume_buy", sa.Numeric(12, 1), nullable=False),
        sa.Column("declared_volume_sell", sa.Numeric(12, 1), nullable=False),
        sa.Column("declared_volume_buy", sa.Numeric(12, 1), nullable=False),
        sa.CheckConstraint("period BETWEEN 1 AND 25", name="ck_dam_prices_period"),
        sa.PrimaryKeyConstraint("delivery_date", "period"),
    )
    op.create_table(
        "dam_days",
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("content_hash", sa.CHAR(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("delivery_date"),
    )
    op.create_table(
        "dam_raw_snapshots",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("quarter", sa.SmallInteger(), nullable=False),
        sa.Column("content_hash", sa.CHAR(64), nullable=False),
        sa.Column("raw_content", sa.LargeBinary(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quarter BETWEEN 1 AND 4", name="ck_dam_raw_snapshots_quarter"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_hash"),
    )


def downgrade() -> None:
    op.drop_table("dam_raw_snapshots")
    op.drop_table("dam_days")
    op.drop_table("dam_prices")
