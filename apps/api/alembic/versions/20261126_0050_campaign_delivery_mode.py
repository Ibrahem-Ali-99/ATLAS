"""Pin the scheduled campaign transport and index provider receipts."""

import sqlalchemy as sa

from alembic import op

revision = "20261126_0050"
down_revision = "20261126_0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column("delivery_mode", sa.String(12), server_default="sandbox", nullable=False),
    )
    op.create_index("ix_campaign_deliveries_message_id", "campaign_deliveries", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_campaign_deliveries_message_id", table_name="campaign_deliveries")
    op.drop_column("campaigns", "delivery_mode")
