"""add provider-backed sender domain verification

Revision ID: 20261123_0016
Revises: 20261123_0015
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20261123_0016"
down_revision: str | None = "20261123_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status = postgresql.ENUM(
        "pending",
        "verified",
        "failed",
        "revoked",
        name="domain_verification_status",
        create_type=False,
    )
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "email_domain_verifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("dns_records", postgresql.JSONB(), nullable=False),
        sa.Column("provider_domain_id", sa.String(length=200), nullable=True),
        sa.Column("evidence", postgresql.JSONB(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "domain", name="uq_email_domain_org"),
    )
    op.create_index("ix_email_domain_verifications_organization_id", "email_domain_verifications", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_email_domain_verifications_organization_id", table_name="email_domain_verifications")
    op.drop_table("email_domain_verifications")
    sa.Enum(name="domain_verification_status").drop(op.get_bind(), checkfirst=True)
