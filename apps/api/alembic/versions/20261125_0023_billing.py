"""add organization billing subscriptions

Revision ID: 20261125_0023
Revises: 20261125_0022
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261125_0023"
down_revision: str | None = "20261125_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status = sa.Enum(
        "trialing",
        "active",
        "past_due",
        "canceled",
        "expired",
        name="subscription_status",
        create_type=False,
    )
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("entitlements", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "organization_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("plan_code", sa.String(32), nullable=False),
        sa.Column("billing_interval", sa.String(16), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_customer_id", sa.String(200)),
        sa.Column("provider_subscription_id", sa.String(200)),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id"),
    )


def downgrade() -> None:
    op.drop_table("organization_subscriptions")
    op.drop_table("subscription_plans")
    status = sa.Enum(name="subscription_status")
    status.drop(op.get_bind(), checkfirst=True)
