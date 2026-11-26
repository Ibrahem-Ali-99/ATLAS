"""Record when an n8n callback signing key was rotated."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261126_0047"
down_revision: str | None = "20261126_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("webhook_keys", sa.Column("rotated_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("webhook_keys", "rotated_at")
