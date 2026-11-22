"""add automation intents, webhooks, email, and calendar records

Revision ID: 20261122_0007
Revises: 20261122_0006
Create Date: 2026-11-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261122_0007"
down_revision: str | None = "20261122_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    intent_status = postgresql.ENUM(
        "pending",
        "dispatching",
        "succeeded",
        "failed",
        "needs_attention",
        name="intent_status",
        create_type=False,
    )
    workflow_kind = postgresql.ENUM(
        "lead_processing",
        "follow_up",
        name="workflow_kind",
        create_type=False,
    )
    workflow_status = postgresql.ENUM(
        "pending",
        "dispatching",
        "accepted",
        "completed",
        "failed",
        "needs_attention",
        "not_configured",
        name="workflow_status",
        create_type=False,
    )
    attempt_outcome = postgresql.ENUM(
        "started",
        "succeeded",
        "failed",
        "uncertain",
        name="attempt_outcome",
        create_type=False,
    )
    email_status = postgresql.ENUM(
        "sent",
        "failed",
        "needs_attention",
        name="email_status",
        create_type=False,
    )
    booking_status = postgresql.ENUM(
        "booked",
        "cancelled",
        name="booking_status",
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
    for enum in (
        intent_status,
        workflow_kind,
        workflow_status,
        attempt_outcome,
        email_status,
        booking_status,
    ):
        enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "webhook_keys",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("secret", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_webhook_keys_organization"),
    )
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("key_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["key_id"], ["webhook_keys.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_id", "idempotency_key", name="uq_webhook_events_key_idempotency"),
    )
    op.create_index("ix_webhook_events_key_id", "webhook_events", ["key_id"])
    op.create_index("ix_webhook_events_organization_id", "webhook_events", ["organization_id"])
    op.create_table(
        "execution_intents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", action, nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("status", intent_status, nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
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
        sa.CheckConstraint(
            "idempotency_key ~ '^[0-9a-f]{64}$'", name="ck_execution_intents_idempotency"
        ),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("approval_id", name="uq_execution_intents_approval"),
        sa.UniqueConstraint("idempotency_key", name="uq_execution_intents_idempotency"),
    )
    op.create_index("ix_execution_intents_organization_id", "execution_intents", ["organization_id"])
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("kind", workflow_kind, nullable=False),
        sa.Column("status", workflow_status, nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=500), nullable=True),
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
        sa.CheckConstraint(
            "idempotency_key ~ '^[0-9a-f]{64}$'", name="ck_workflow_runs_idempotency"
        ),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_workflow_runs_idempotency"),
    )
    op.create_index("ix_workflow_runs_organization_id", "workflow_runs", ["organization_id"])
    op.create_table(
        "execution_attempts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("intent_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", attempt_outcome, nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(intent_id IS NOT NULL) <> (workflow_run_id IS NOT NULL)",
            name="ck_execution_attempts_one_parent",
        ),
        sa.ForeignKeyConstraint(["intent_id"], ["execution_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_execution_attempts_organization_id", "execution_attempts", ["organization_id"])
    op.create_table(
        "email_messages",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("intent_id", sa.Uuid(), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", email_status, nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("provider_message_id", sa.String(length=200), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["intent_id"], ["execution_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("intent_id", name="uq_email_messages_intent"),
    )
    op.create_index("ix_email_messages_organization_id", "email_messages", ["organization_id"])
    op.create_table(
        "calendar_bookings",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("intent_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", booking_status, nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.String(length=200), nullable=True),
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
        sa.ForeignKeyConstraint(["intent_id"], ["execution_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("intent_id", name="uq_calendar_bookings_intent"),
    )
    op.create_index("ix_calendar_bookings_organization_id", "calendar_bookings", ["organization_id"])
    for table in ("execution_intents", "workflow_runs", "calendar_bookings"):
        op.execute(
            f"""
            CREATE TRIGGER {table}_set_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
            """
        )


def downgrade() -> None:
    for table in ("calendar_bookings", "workflow_runs", "execution_intents"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_set_updated_at ON {table}")
    op.drop_index("ix_calendar_bookings_organization_id", table_name="calendar_bookings")
    op.drop_table("calendar_bookings")
    op.drop_index("ix_email_messages_organization_id", table_name="email_messages")
    op.drop_table("email_messages")
    op.drop_index("ix_execution_attempts_organization_id", table_name="execution_attempts")
    op.drop_table("execution_attempts")
    op.drop_index("ix_workflow_runs_organization_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_index("ix_execution_intents_organization_id", table_name="execution_intents")
    op.drop_table("execution_intents")
    op.drop_index("ix_webhook_events_organization_id", table_name="webhook_events")
    op.drop_index("ix_webhook_events_key_id", table_name="webhook_events")
    op.drop_table("webhook_events")
    op.drop_table("webhook_keys")
    for name in (
        "booking_status",
        "email_status",
        "attempt_outcome",
        "workflow_status",
        "workflow_kind",
        "intent_status",
    ):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
