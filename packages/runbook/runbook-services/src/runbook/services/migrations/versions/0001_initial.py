"""Create Runbook service configuration and run tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the initial service tables and indexes."""
    op.create_table(
        "config_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("config_id", sa.String(length=255), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "config_id", "revision", name="uq_config_revision"),
    )
    op.create_index("ix_config_revisions_kind", "config_revisions", ["kind"])
    op.create_index("ix_config_revisions_config_id", "config_revisions", ["config_id"])
    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.String(length=255), nullable=False),
        sa.Column("slot", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("force", sa.Boolean(), nullable=False),
        sa.Column("config_revision", sa.Integer(), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("identity_key", sa.String(length=512)),
        sa.Column("snapshot_id", sa.String(length=128)),
        sa.Column("context_hash", sa.String(length=128)),
        sa.Column("code_version", sa.String(length=255)),
        sa.Column("artifact_id", sa.String(length=128)),
        sa.Column("result", sa.JSON().with_variant(postgresql.JSONB(), "postgresql")),
        sa.Column("reason", sa.Text()),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("run_id"),
    )
    for name, columns in (
        ("ix_runs_kind", ["kind"]),
        ("ix_runs_target_id", ["target_id"]),
        ("ix_runs_slot", ["slot"]),
        ("ix_runs_status", ["status"]),
        ("ix_runs_identity_key", ["identity_key"]),
    ):
        op.create_index(name, "runs", columns)


def downgrade() -> None:
    """Remove the initial service tables."""
    op.drop_table("runs")
    op.drop_table("config_revisions")
