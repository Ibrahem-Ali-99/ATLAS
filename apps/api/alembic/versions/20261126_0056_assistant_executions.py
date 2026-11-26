"""Persist Assistant tool executions separately from inquiry agent runs."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20261126_0056"
down_revision = "20261126_0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_executions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("user_message_id", sa.Uuid(), nullable=True),
        sa.Column("assistant_message_id", sa.Uuid(), nullable=True),
        sa.Column("request", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("selected_tools", JSONB(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_assistant_executions_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assistant_message_id"], ["messages.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_assistant_executions_organization_id",
        "assistant_executions",
        ["organization_id"],
    )
    op.create_index(
        "ix_assistant_executions_conversation_id",
        "assistant_executions",
        ["conversation_id"],
    )
    op.create_table(
        "assistant_execution_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(80), nullable=False),
        sa.Column("arguments", JSONB(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("records", JSONB(), nullable=False),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("recovery", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed', 'recovered')",
            name="ck_assistant_execution_steps_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["assistant_executions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_assistant_execution_steps_organization_id",
        "assistant_execution_steps",
        ["organization_id"],
    )
    op.create_index(
        "ix_assistant_execution_steps_execution_id",
        "assistant_execution_steps",
        ["execution_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_assistant_execution_steps_execution_id", table_name="assistant_execution_steps"
    )
    op.drop_index(
        "ix_assistant_execution_steps_organization_id", table_name="assistant_execution_steps"
    )
    op.drop_table("assistant_execution_steps")
    op.drop_index("ix_assistant_executions_conversation_id", table_name="assistant_executions")
    op.drop_index("ix_assistant_executions_organization_id", table_name="assistant_executions")
    op.drop_table("assistant_executions")
