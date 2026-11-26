"""Persist campaign schedules and individual delivery outcomes."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261126_0046"
down_revision: str | None = "20261125_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("scheduled_at", sa.DateTime(timezone=True)))
    op.add_column("campaigns", sa.Column("finished_at", sa.DateTime(timezone=True)))
    op.create_index("ix_campaigns_dispatch", "campaigns", ["status", "scheduled_at"])
    op.create_table(
        "campaign_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("message_id", sa.String(255)),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("campaign_id", "email", name="uq_campaign_deliveries_email"),
    )
    op.create_index(
        "ix_campaign_deliveries_queue", "campaign_deliveries", ["campaign_id", "status", "id"]
    )


def downgrade() -> None:
    op.drop_table("campaign_deliveries")
    op.drop_index("ix_campaigns_dispatch", table_name="campaigns")
    op.drop_column("campaigns", "finished_at")
    op.drop_column("campaigns", "scheduled_at")
