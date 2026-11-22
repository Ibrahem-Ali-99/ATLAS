import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.automation.models import (
    CalendarBooking,
    EmailMessage,
    ExecutionAttempt,
    WebhookKey,
    WorkflowRun,
)


def snapshot(db: Session, organization_id: uuid.UUID) -> dict[str, Any]:
    settings = get_settings()
    key = db.scalar(select(WebhookKey.id).where(WebhookKey.organization_id == organization_id))
    runs = list(
        db.scalars(
            select(WorkflowRun)
            .where(WorkflowRun.organization_id == organization_id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(20)
        )
    )
    run_ids = [run.id for run in runs]
    attempts = []
    if run_ids:
        attempts = list(
            db.scalars(
                select(ExecutionAttempt)
                .where(ExecutionAttempt.workflow_run_id.in_(run_ids))
                .order_by(ExecutionAttempt.started_at.asc())
            )
        )
    emails = list(
        db.scalars(
            select(EmailMessage)
            .where(EmailMessage.organization_id == organization_id)
            .order_by(EmailMessage.created_at.desc())
            .limit(20)
        )
    )
    bookings = list(
        db.scalars(
            select(CalendarBooking)
            .where(CalendarBooking.organization_id == organization_id)
            .order_by(CalendarBooking.created_at.desc())
            .limit(20)
        )
    )
    return {
        "email_mode": settings.email_mode,
        "calendar_provider": "simulation",
        "n8n_configured": bool(settings.n8n_lead_webhook_url),
        "webhook_configured": key is not None,
        "automations": [
            {
                "name": "Lead processing",
                "trigger": "lead_created",
                "description": "A new lead asks n8n to call ATLAS back and record the outcome.",
            },
            {
                "name": "Follow-up",
                "trigger": "schedule",
                "description": "n8n opens a follow-up approval. Sending waits for an admin.",
            },
        ],
        "runs": [
            {
                "id": run.id,
                "kind": run.kind.value,
                "status": run.status.value,
                "lead_id": run.lead_id,
                "agent_run_id": run.agent_run_id,
                "attempt_count": run.attempt_count,
                "last_error": run.last_error,
                "created_at": run.created_at,
                "attempts": [
                    {
                        "outcome": attempt.outcome.value,
                        "error": attempt.error,
                        "external_id": attempt.external_id,
                        "started_at": attempt.started_at,
                    }
                    for attempt in attempts
                    if attempt.workflow_run_id == run.id
                ],
            }
            for run in runs
        ],
        "emails": [
            {
                "id": email.id,
                "lead_id": email.lead_id,
                "status": email.status.value,
                "mode": email.mode,
                "provider_message_id": email.provider_message_id,
                "error": email.error,
                "sent_at": email.sent_at,
            }
            for email in emails
        ],
        "bookings": [
            {
                "id": booking.id,
                "lead_id": booking.lead_id,
                "status": booking.status.value,
                "provider": booking.provider,
                "starts_at": booking.starts_at,
                "ends_at": booking.ends_at,
                "provider_event_id": booking.provider_event_id,
            }
            for booking in bookings
        ],
    }
