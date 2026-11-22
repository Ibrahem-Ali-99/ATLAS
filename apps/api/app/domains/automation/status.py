import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.approvals.models import ActionType, Approval, ApprovalStatus
from app.domains.automation.models import (
    CalendarBooking,
    EmailMessage,
    ExecutionAttempt,
    WebhookKey,
    WorkflowRun,
)
from app.domains.crm.models import Company, Lead


def snapshot(db: Session, organization_id: uuid.UUID) -> dict[str, Any]:
    settings = get_settings()
    key = db.scalar(select(WebhookKey.id).where(WebhookKey.organization_id == organization_id))
    counts = _status_counts(db, organization_id)
    awaiting_review = _awaiting_review(db, organization_id)
    webhook_ready = key is not None
    lead_ready = bool(settings.n8n_lead_webhook_url) and webhook_ready
    runs = list(
        db.scalars(
            select(WorkflowRun)
            .where(WorkflowRun.organization_id == organization_id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(20)
        )
    )
    records = _lead_records(db, organization_id, [run.lead_id for run in runs if run.lead_id])
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
            _card(
                "Lead processing",
                "lead_created",
                "A new lead asks n8n to call ATLAS back and record the outcome.",
                "lead_processing",
                counts.get("lead_processing", {}),
                0,
                lead_ready,
            ),
            _card(
                "Follow-up",
                "schedule",
                "n8n opens a follow-up approval. Sending waits for an admin.",
                "follow_up",
                counts.get("follow_up", {}),
                awaiting_review,
                webhook_ready,
            ),
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
                "lead_title": records.get(run.lead_id, (None, None))[0] if run.lead_id else None,
                "company_name": records.get(run.lead_id, (None, None))[1] if run.lead_id else None,
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


def _card(
    name: str,
    trigger: str,
    description: str,
    kind: str,
    counts: dict[str, int],
    awaiting_review: int,
    configured: bool,
) -> dict[str, Any]:
    return {
        "name": name,
        "trigger": trigger,
        "description": description,
        "kind": kind,
        "completed": counts.get("completed", 0),
        "awaiting_review": awaiting_review,
        "needs_attention": counts.get("needs_attention", 0),
        "failed": counts.get("failed", 0),
        "configured": configured,
    }


def _status_counts(db: Session, organization_id: uuid.UUID) -> dict[str, dict[str, int]]:
    rows = db.execute(
        select(WorkflowRun.kind, WorkflowRun.status, func.count())
        .where(WorkflowRun.organization_id == organization_id)
        .group_by(WorkflowRun.kind, WorkflowRun.status)
    ).all()
    grouped: dict[str, dict[str, int]] = {}
    for kind, status, count in rows:
        grouped.setdefault(kind.value, {})[status.value] = int(count)
    return grouped


def _awaiting_review(db: Session, organization_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Approval)
            .where(
                Approval.organization_id == organization_id,
                Approval.status == ApprovalStatus.pending,
                Approval.action_type.in_(
                    (ActionType.prepare_customer_response, ActionType.request_appointment)
                ),
            )
        )
        or 0
    )


def _lead_records(
    db: Session, organization_id: uuid.UUID, lead_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, str | None]]:
    if not lead_ids:
        return {}
    leads = list(
        db.scalars(
            select(Lead).where(Lead.organization_id == organization_id, Lead.id.in_(lead_ids))
        )
    )
    company_ids = [lead.company_id for lead in leads if lead.company_id is not None]
    companies = []
    if company_ids:
        companies = list(
            db.scalars(
                select(Company).where(
                    Company.organization_id == organization_id, Company.id.in_(company_ids)
                )
            )
        )
    names = {company.id: company.name for company in companies}
    return {
        lead.id: (lead.title, names.get(lead.company_id) if lead.company_id else None)
        for lead in leads
    }
