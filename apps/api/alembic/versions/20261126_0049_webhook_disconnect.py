"""Allow webhook credentials to be disconnected without deleting history."""

import sqlalchemy as sa

from alembic import op

revision = "20261126_0049"
down_revision = "20261126_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("webhook_keys", sa.Column("revoked_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("webhook_keys", "revoked_at")
