"""Add immutable historical source request fields to the durable run ledger."""

import sqlalchemy as sa
from alembic import op

revision = "0004_historical_source_runs"
down_revision = "0003_addressable_workers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add mode and optional inclusive historical dates to existing runs."""
    op.add_column("runs", sa.Column("mode", sa.String(length=16), nullable=False, server_default="normal"))
    op.add_column("runs", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("runs", sa.Column("end_date", sa.Date(), nullable=True))
    op.create_index("ix_runs_mode", "runs", ["mode"])


def downgrade() -> None:
    """Remove historical source request fields."""
    op.drop_index("ix_runs_mode", table_name="runs")
    op.drop_column("runs", "end_date")
    op.drop_column("runs", "start_date")
    op.drop_column("runs", "mode")
