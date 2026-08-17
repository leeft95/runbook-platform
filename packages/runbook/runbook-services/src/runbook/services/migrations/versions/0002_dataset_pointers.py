"""Create the data-owned current dataset pointer table."""

import sqlalchemy as sa
from alembic import op

revision = "0002_dataset_pointers"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the current pointer registry used by service-coordinated runs."""
    op.create_table(
        "dataset_pointers",
        sa.Column("dataset_id", sa.String(length=255), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("manifest_ref", sa.String(length=1024), nullable=False),
        sa.Column("watermark", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_run_id", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("dataset_id"),
    )
    op.create_index("ix_dataset_pointers_source_id", "dataset_pointers", ["source_id"])


def downgrade() -> None:
    """Remove the current pointer registry."""
    op.drop_index("ix_dataset_pointers_source_id", table_name="dataset_pointers")
    op.drop_table("dataset_pointers")
