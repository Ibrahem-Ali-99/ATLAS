"""Keep assistant conversations and record proposed business actions."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20261126_0054"
down_revision = "20261126_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("conversations", sa.Column("archived_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_conversations_archived_by_users",
        "conversations",
        "users",
        ["archived_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "assistant_proposals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["workflow_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "kind IN ('follow_up', 'appointment', 'task')",
            name="ck_assistant_proposals_kind",
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'submitted', 'dismissed')",
            name="ck_assistant_proposals_status",
        ),
    )
    op.create_index(
        "ix_assistant_proposals_organization_id",
        "assistant_proposals",
        ["organization_id"],
    )
    op.create_index(
        "ix_assistant_proposals_conversation_id",
        "assistant_proposals",
        ["conversation_id"],
    )
    op.create_index("ix_assistant_proposals_message_id", "assistant_proposals", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_assistant_proposals_message_id", table_name="assistant_proposals")
    op.drop_index("ix_assistant_proposals_conversation_id", table_name="assistant_proposals")
    op.drop_index("ix_assistant_proposals_organization_id", table_name="assistant_proposals")
    op.drop_table("assistant_proposals")
    op.drop_constraint("fk_conversations_archived_by_users", "conversations", type_="foreignkey")
    op.drop_column("conversations", "archived_by")
    op.drop_column("conversations", "archived_at")
