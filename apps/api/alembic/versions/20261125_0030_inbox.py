"""add unified customer inbox"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261125_0030"
down_revision: str | None = "20261125_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status = sa.Enum("open", "pending", "resolved", name="inbox_status", create_type=False)
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "inbox_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid()),
        sa.Column("lead_id", sa.Uuid()),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("assigned_to", sa.Uuid()),
        sa.Column("unread_count", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "inbox_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("sender", sa.String(320), nullable=False),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("delivery_status", sa.String(24), nullable=False),
        sa.Column("provider_message_id", sa.String(200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["inbox_conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "provider_message_id", name="uq_inbox_provider_message"
        ),
    )


def downgrade() -> None:
    op.drop_table("inbox_messages")
    op.drop_table("inbox_conversations")
    sa.Enum(name="inbox_status").drop(op.get_bind(), checkfirst=True)
