"""Persist public inference spend and the administrator kill switch."""

import sqlalchemy as sa

from alembic import op

revision = "20261127_0057"
down_revision = "20261126_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "public_inference_control",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("killed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_public_inference_control_singleton"),
    )
    op.create_table(
        "public_inference_spend",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("session_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_micros", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('reserved', 'settled')",
            name="ck_public_inference_spend_status",
        ),
        sa.CheckConstraint("input_tokens >= 0", name="ck_public_inference_spend_input"),
        sa.CheckConstraint("output_tokens >= 0", name="ck_public_inference_spend_output"),
        sa.CheckConstraint("cost_micros >= 0", name="ck_public_inference_spend_cost"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_public_inference_spend_organization_id",
        "public_inference_spend",
        ["organization_id"],
    )
    op.create_index(
        "ix_public_inference_spend_session_created",
        "public_inference_spend",
        ["session_key", "created_at"],
    )
    op.create_index(
        "ix_public_inference_spend_created_at",
        "public_inference_spend",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_public_inference_spend_created_at", table_name="public_inference_spend")
    op.drop_index(
        "ix_public_inference_spend_session_created", table_name="public_inference_spend"
    )
    op.drop_index(
        "ix_public_inference_spend_organization_id", table_name="public_inference_spend"
    )
    op.drop_table("public_inference_spend")
    op.drop_table("public_inference_control")
