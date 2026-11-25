"""add billing period start for usage accounting"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261125_0025"
down_revision: str | None = "20261125_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organization_subscriptions",
        sa.Column("current_period_start", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_column("organization_subscriptions", "current_period_start")
