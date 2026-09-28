"""Create Telegram recipients and notification deliveries.

Revision ID: 0003_telegram
Revises: 0002_collection_runs
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_telegram"
down_revision = "0002_collection_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_recipients",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id"),
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'sent', 'failed')", name="ck_notification_deliveries_status"),
        sa.ForeignKeyConstraint(["run_id"], ["collection_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "chat_id", name="uq_notification_deliveries_run_chat"),
    )


def downgrade() -> None:
    op.drop_table("notification_deliveries")
    op.drop_table("telegram_recipients")
