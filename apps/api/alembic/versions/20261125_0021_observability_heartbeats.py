"""persist background worker heartbeats

Revision ID: 20261125_0021
Revises: 20261124_0020
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261125_0021"
down_revision: str | None = "20261124_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.String(length=120), nullable=False),
        sa.Column("worker_kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("worker_id", name="uq_worker_heartbeats_worker_id"),
    )
    op.create_index("ix_worker_heartbeats_kind", "worker_heartbeats", ["worker_kind"])


def downgrade() -> None:
    op.drop_index("ix_worker_heartbeats_kind", table_name="worker_heartbeats")
    op.drop_table("worker_heartbeats")
