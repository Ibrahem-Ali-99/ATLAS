import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.approvals.models import ACTION_TYPE, ActionType
from app.domains.provenance.origin import Origin, origin_column


class IntentStatus(enum.StrEnum):
    pending = "pending"
    dispatching = "dispatching"
    succeeded = "succeeded"
    failed = "failed"
    needs_attention = "needs_attention"


class WorkflowKind(enum.StrEnum):
    lead_processing = "lead_processing"
    follow_up = "follow_up"


class WorkflowStatus(enum.StrEnum):
    pending = "pending"
    dispatching = "dispatching"
    accepted = "accepted"
    completed = "completed"
    failed = "failed"
    needs_attention = "needs_attention"
    not_configured = "not_configured"


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_workflow_definitions_org_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class WorkflowTask(Base):
    __tablename__ = "workflow_tasks"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True
    )
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="workflow")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AttemptOutcome(enum.StrEnum):
    started = "started"
    succeeded = "succeeded"
    failed = "failed"
    uncertain = "uncertain"


class EmailStatus(enum.StrEnum):
    sent = "sent"
    failed = "failed"
    needs_attention = "needs_attention"


class BookingStatus(enum.StrEnum):
    booked = "booked"
    cancelled = "cancelled"


def _enum(enum_type: type[enum.StrEnum], name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        values_callable=lambda members: [member.value for member in members],
        native_enum=True,
        create_type=False,
    )


INTENT_STATUS = _enum(IntentStatus, "intent_status")
WORKFLOW_KIND = _enum(WorkflowKind, "workflow_kind")
WORKFLOW_STATUS = _enum(WorkflowStatus, "workflow_status")
ATTEMPT_OUTCOME = _enum(AttemptOutcome, "attempt_outcome")
EMAIL_STATUS = _enum(EmailStatus, "email_status")
BOOKING_STATUS = _enum(BookingStatus, "booking_status")


class WebhookKey(Base):
    __tablename__ = "webhook_keys"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_webhook_keys_organization"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    secret: Mapped[str] = mapped_column(Text, nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("key_id", "idempotency_key", name="uq_webhook_events_key_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("webhook_keys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExecutionIntent(Base):
    __tablename__ = "execution_intents"
    __table_args__ = (
        UniqueConstraint("approval_id", name="uq_execution_intents_approval"),
        UniqueConstraint("idempotency_key", name="uq_execution_intents_idempotency"),
        CheckConstraint(
            "idempotency_key ~ '^[0-9a-f]{64}$'", name="ck_execution_intents_idempotency"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    approval_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("approvals.id", ondelete="CASCADE"), nullable=False
    )
    action_type: Mapped[ActionType] = mapped_column(ACTION_TYPE, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[IntentStatus] = mapped_column(INTENT_STATUS, nullable=False)
    origin: Mapped[Origin] = origin_column()
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_workflow_runs_idempotency"),
        CheckConstraint("idempotency_key ~ '^[0-9a-f]{64}$'", name="ck_workflow_runs_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[WorkflowKind] = mapped_column(WORKFLOW_KIND, nullable=False)
    status: Mapped[WorkflowStatus] = mapped_column(WORKFLOW_STATUS, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True
    )
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    origin: Mapped[Origin] = origin_column()
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ExecutionAttempt(Base):
    __tablename__ = "execution_attempts"
    __table_args__ = (
        CheckConstraint(
            "(intent_id IS NOT NULL) <> (workflow_run_id IS NOT NULL)",
            name="ck_execution_attempts_one_parent",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    intent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("execution_intents.id", ondelete="CASCADE"), nullable=True
    )
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=True
    )
    outcome: Mapped[AttemptOutcome] = mapped_column(ATTEMPT_OUTCOME, nullable=False)
    origin: Mapped[Origin] = origin_column()
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailMessage(Base):
    __tablename__ = "email_messages"
    __table_args__ = (UniqueConstraint("intent_id", name="uq_email_messages_intent"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("inbox_conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    intent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("execution_intents.id", ondelete="CASCADE"), nullable=False
    )
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[EmailStatus] = mapped_column(EMAIL_STATUS, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    origin: Mapped[Origin] = origin_column()
    provider_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CalendarBooking(Base):
    __tablename__ = "calendar_bookings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    intent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("execution_intents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[BookingStatus] = mapped_column(BOOKING_STATUS, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    origin: Mapped[Origin] = origin_column()
    provider_event_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider_calendar_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
