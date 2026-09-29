"""Add the global notifications switch to app settings.

Revision ID: 0005_notifications_enabled
Revises: 0004_app_settings
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_notifications_enabled"
down_revision = "0004_app_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "notifications_enabled")
