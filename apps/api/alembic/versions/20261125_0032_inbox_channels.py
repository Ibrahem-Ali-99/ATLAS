"""add inbox channel metadata and website chat widgets"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261125_0032"
down_revision: str | None = "20261125_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inbox_conversations",
        sa.Column("channel", sa.String(24), nullable=False, server_default="email"),
    )
    op.add_column(
        "inbox_messages",
        sa.Column("channel", sa.String(24), nullable=False, server_default="email"),
    )
    op.create_table(
        "inbox_widget_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.String(64), nullable=False),
        sa.Column("allowed_domains", postgresql.JSONB(), nullable=False),
        sa.Column("appearance", postgresql.JSONB(), nullable=False),
        sa.Column("welcome_message", sa.String(500), nullable=False),
        sa.Column("operating_mode", sa.String(24), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_inbox_widget_configs_public_id", "inbox_widget_configs", ["public_id"])
    op.create_table(
        "inbox_widget_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("widget_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("visitor_token_hash", sa.String(128), nullable=False),
        sa.Column("origin", sa.String(300), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["widget_id"], ["inbox_widget_configs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["inbox_conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id"),
        sa.UniqueConstraint("visitor_token_hash"),
    )
    op.create_index("ix_inbox_widget_sessions_widget_id", "inbox_widget_sessions", ["widget_id"])


def downgrade() -> None:
    op.drop_index("ix_inbox_widget_sessions_widget_id", table_name="inbox_widget_sessions")
    op.drop_table("inbox_widget_sessions")
    op.drop_index("ix_inbox_widget_configs_public_id", table_name="inbox_widget_configs")
    op.drop_table("inbox_widget_configs")
    op.drop_column("inbox_messages", "channel")
    op.drop_column("inbox_conversations", "channel")
