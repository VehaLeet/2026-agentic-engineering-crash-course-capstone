"""Create collection run log.

Revision ID: 0002_collection_runs
Revises: 0001_dam_storage
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_collection_runs"
down_revision = "0001_dam_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collection_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column(
            "changed_days", postgresql.ARRAY(sa.Date()), nullable=False,
            server_default=sa.text("'{}'::date[]"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IS NULL OR status IN ('success', 'no_changes', 'no_data', 'error', 'skipped_locked')",
            name="ck_collection_runs_status",
        ),
        sa.CheckConstraint("trigger IN ('scheduled', 'manual')", name="ck_collection_runs_trigger"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_collection_runs_started_at", "collection_runs", [sa.text("started_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_collection_runs_started_at", table_name="collection_runs")
    op.drop_table("collection_runs")
