"""create agent runs, events, and approvals

Revision ID: 20261122_0005
Revises: 20261122_0004
Create Date: 2026-11-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261122_0005"
down_revision: str | None = "20261122_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    run_status = postgresql.ENUM(
        "running",
        "awaiting_approval",
        "completed",
        "failed",
        name="agent_run_status",
        create_type=False,
    )
    action = postgresql.ENUM(
        "create_lead",
        "update_lead",
        "prepare_customer_response",
        "request_appointment",
        name="approval_action",
        create_type=False,
    )
    approval_status = postgresql.ENUM(
        "pending",
        "approved",
        "rejected",
        "executing",
        "executed",
        "failed",
        "expired",
        name="approval_status",
        create_type=False,
    )
    run_status.create(op.get_bind(), checkfirst=True)
    action.create(op.get_bind(), checkfirst=True)
    approval_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("inquiry_id", sa.Uuid(), nullable=False),
        sa.Column("started_by", sa.Uuid(), nullable=False),
        sa.Column("status", run_status, nullable=False),
        sa.Column("qualification", sa.String(length=40), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["inquiry_id"], ["inquiries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["started_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_organization_id", "agent_runs", ["organization_id"])
    op.create_index("ix_agent_runs_inquiry_id", "agent_runs", ["inquiry_id"])
    op.create_table(
        "agent_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_events_organization_id", "agent_events", ["organization_id"])
    op.create_index("ix_agent_events_run_id", "agent_events", ["run_id"])
    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("action_type", action, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("status", approval_status, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("execution_error", sa.String(length=500), nullable=True),
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
        sa.CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="ck_approvals_payload_hash"),
        sa.CheckConstraint("position >= 0", name="ck_approvals_position"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "action_type", name="uq_approvals_run_action"),
        sa.UniqueConstraint("run_id", "position", name="uq_approvals_run_position"),
    )
    op.create_index("ix_approvals_organization_id", "approvals", ["organization_id"])
    op.create_index("ix_approvals_run_id", "approvals", ["run_id"])
    op.execute(
        """
        CREATE TRIGGER agent_runs_set_updated_at
        BEFORE UPDATE ON agent_runs
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER approvals_set_updated_at
        BEFORE UPDATE ON approvals
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS approvals_set_updated_at ON approvals")
    op.execute("DROP TRIGGER IF EXISTS agent_runs_set_updated_at ON agent_runs")
    op.drop_index("ix_approvals_run_id", table_name="approvals")
    op.drop_index("ix_approvals_organization_id", table_name="approvals")
    op.drop_table("approvals")
    op.drop_index("ix_agent_events_run_id", table_name="agent_events")
    op.drop_index("ix_agent_events_organization_id", table_name="agent_events")
    op.drop_table("agent_events")
    op.drop_index("ix_agent_runs_inquiry_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_organization_id", table_name="agent_runs")
    op.drop_table("agent_runs")
    postgresql.ENUM(name="approval_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="approval_action").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="agent_run_status").drop(op.get_bind(), checkfirst=True)
