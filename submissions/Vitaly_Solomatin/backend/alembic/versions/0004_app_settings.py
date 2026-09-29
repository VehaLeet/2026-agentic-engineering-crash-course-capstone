"""Create single-row app settings with the collection schedule.

Revision ID: 0004_app_settings
Revises: 0003_telegram
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_app_settings"
down_revision = "0003_telegram"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("schedule_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("collect_interval_minutes", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("id = 1", name="ck_app_settings_single_row"),
        sa.CheckConstraint(
            "collect_interval_minutes BETWEEN 5 AND 1440", name="ck_app_settings_collect_interval"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("INSERT INTO app_settings (id) VALUES (1)")


def downgrade() -> None:
    op.drop_table("app_settings")
