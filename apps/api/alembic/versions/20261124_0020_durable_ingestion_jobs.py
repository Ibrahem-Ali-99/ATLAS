"""add durable knowledge ingestion jobs

Revision ID: 20261124_0020
Revises: 20261124_0019
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261124_0020"
down_revision: str | None = "20261124_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status = postgresql.ENUM(
        "queued",
        "running",
        "retrying",
        "succeeded",
        "failed",
        name="ingestion_job_status",
        create_type=False,
    )
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_ingestion_jobs_organization_id", "ingestion_jobs", ["organization_id"])
    op.create_index("ix_ingestion_jobs_claimable", "ingestion_jobs", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_claimable", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_organization_id", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    postgresql.ENUM(name="ingestion_job_status", create_type=False).drop(
        op.get_bind(), checkfirst=True
    )
