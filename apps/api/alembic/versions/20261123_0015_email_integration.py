"""add organization-scoped email integration metadata

Revision ID: 20261123_0015
Revises: 20261123_0014
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261123_0015"
down_revision: str | None = "20261123_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE integration_type ADD VALUE IF NOT EXISTS 'email'")
    op.add_column("integration_configs", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("integration_configs", sa.Column("verification_detail", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("integration_configs", "verification_detail")
    op.drop_column("integration_configs", "verified_at")
    # PostgreSQL enum values cannot be removed safely in a transactional downgrade.
