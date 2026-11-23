import uuid
from datetime import datetime

from pydantic import BaseModel


class WebhookKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    secret: str


class AttemptOut(BaseModel):
    outcome: str
    error: str | None
    external_id: str | None
    started_at: datetime


class WorkflowRunOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    lead_id: uuid.UUID | None
    agent_run_id: uuid.UUID | None
    attempt_count: int
    last_error: str | None
    created_at: datetime
    lead_title: str | None = None
    company_name: str | None = None
    attempts: list[AttemptOut]


class EmailDeliveryOut(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID | None
    status: str
    mode: str
    provider_message_id: str | None
    error: str | None
    sent_at: datetime | None
    subject: str | None = None
    recipient: str | None = None
    approval_id: uuid.UUID | None = None
    intent_id: uuid.UUID | None = None
    attempt_count: int = 0
    queued_at: datetime | None = None
    attempted_at: datetime | None = None
    completed_at: datetime | None = None
    lead_title: str | None = None
    company_name: str | None = None
    state: str | None = None


class EmailActivityOut(EmailDeliveryOut):
    body: str | None = None
    attempts: list[AttemptOut] = []


class BookingOut(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    status: str
    provider: str
    starts_at: datetime
    ends_at: datetime
    provider_event_id: str | None


class AutomationCard(BaseModel):
    name: str
    trigger: str
    description: str
    kind: str
    completed: int
    awaiting_review: int
    needs_attention: int
    failed: int
    configured: bool


class AutomationSnapshot(BaseModel):
    email_mode: str
    calendar_provider: str
    n8n_configured: bool
    webhook_configured: bool
    automations: list[AutomationCard]
    runs: list[WorkflowRunOut]
    emails: list[EmailDeliveryOut]
    bookings: list[BookingOut]
