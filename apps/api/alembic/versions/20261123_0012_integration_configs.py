"""organization-scoped integration configuration foundation

Revision ID: 20261123_0012
Revises: 20261122_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261123_0012"
down_revision: str | None = "20261122_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    integration_type = sa.Enum("chat", "embedding", "n8n", name="integration_type", create_type=False)
    integration_status = sa.Enum("configured", "disabled", "verification_failed", name="integration_status", create_type=False)
    integration_type.create(op.get_bind(), checkfirst=True)
    integration_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "integration_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("integration_type", integration_type, nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("encrypted_credentials", sa.Text(), nullable=True),
        sa.Column("status", integration_status, nullable=False),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "integration_type", name="uq_integration_configs_org_type"),
    )
    op.create_index("ix_integration_configs_organization_id", "integration_configs", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_integration_configs_organization_id", table_name="integration_configs")
    op.drop_table("integration_configs")
    sa.Enum(name="integration_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="integration_type").drop(op.get_bind(), checkfirst=True)
