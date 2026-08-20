"""Add durable state for addressable local workers."""

import sqlalchemy as sa
from alembic import op

revision = "0003_addressable_workers"
down_revision = "0002_dataset_pointers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add worker ownership, cancellation, snapshot, and dependency fields."""
    op.add_column("runs", sa.Column("worker_id", sa.String(length=255), nullable=True))
    op.add_column("runs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("runs", sa.Column("snapshot_payload", sa.JSON(), nullable=True))
    op.add_column("runs", sa.Column("dependencies_released_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_runs_worker_id", "runs", ["worker_id"])


def downgrade() -> None:
    """Remove addressable worker state."""
    op.drop_index("ix_runs_worker_id", table_name="runs")
    op.drop_column("runs", "dependencies_released_at")
    op.drop_column("runs", "snapshot_payload")
    op.drop_column("runs", "cancel_requested_at")
    op.drop_column("runs", "worker_id")
