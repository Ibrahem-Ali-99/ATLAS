import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.approvals.models import ActionType, Approval, ApprovalStatus
from app.domains.automation.models import (
    CalendarBooking,
    EmailMessage,
    EmailStatus,
    ExecutionAttempt,
    ExecutionIntent,
    IntentStatus,
    WebhookKey,
    WorkflowRun,
)
from app.domains.crm.models import Company, Lead
from app.domains.provenance.origin import DataScope, scope_clause
from app.integrations.google_calendar import active_connection


def snapshot(
    db: Session, organization_id: uuid.UUID, scope: DataScope = DataScope.operational
) -> dict[str, Any]:
    settings = get_settings()
    key = db.scalar(
        select(WebhookKey.id).where(
            WebhookKey.organization_id == organization_id, WebhookKey.revoked_at.is_(None)
        )
    )
    counts = _status_counts(db, organization_id, scope)
    awaiting_review = _awaiting_review(db, organization_id, scope)
    webhook_ready = key is not None
    lead_ready = bool(settings.n8n_lead_webhook_url) and webhook_ready
    runs = list(
        db.scalars(
            select(WorkflowRun)
            .where(*_scoped(WorkflowRun, organization_id, scope))
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
    email_activity = _email_activity(db, organization_id, scope)
    bookings = list(
        db.scalars(
            select(CalendarBooking)
            .where(*_scoped(CalendarBooking, organization_id, scope))
            .order_by(CalendarBooking.created_at.desc())
            .limit(20)
        )
    )
    return {
        "email_mode": settings.email_mode,
        "calendar_provider": "google" if active_connection(db, organization_id) else "simulation",
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
        "emails": email_activity,
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


def _email_activity(
    db: Session, organization_id: uuid.UUID, scope: DataScope
) -> list[dict[str, Any]]:
    messages = list(
        db.scalars(
            select(EmailMessage)
            .where(*_scoped(EmailMessage, organization_id, scope))
            .order_by(EmailMessage.created_at.desc())
            .limit(50)
        )
    )
    message_by_intent = {message.intent_id: message for message in messages}
    intents = list(
        db.scalars(
            select(ExecutionIntent)
            .where(
                *_scoped(ExecutionIntent, organization_id, scope),
                ExecutionIntent.action_type == ActionType.prepare_customer_response,
                func.coalesce(ExecutionIntent.payload["channel"].as_string(), "email") == "email",
            )
            .order_by(ExecutionIntent.created_at.desc())
            .limit(50)
        )
    )
    result: list[dict[str, Any]] = []
    for intent in intents:
        payload = intent.payload if isinstance(intent.payload, dict) else {}
        message = message_by_intent.get(intent.id)
        approval = db.get(Approval, intent.approval_id)
        approval_status = approval.status.value if approval else None
        status_value = message.status.value if message else intent.status.value
        state = _email_state(status_value, approval_status)
        attempts = list(
            db.scalars(
                select(ExecutionAttempt)
                .where(ExecutionAttempt.intent_id == intent.id)
                .order_by(ExecutionAttempt.started_at.asc())
            )
        )
        result.append(
            {
                "id": message.id if message else intent.id,
                "lead_id": _uuid_or_none(payload.get("lead_id")),
                "status": message.status.value if message else intent.status.value,
                "state": state,
                "mode": message.mode if message else payload.get("delivery_mode", "sandbox"),
                "provider_message_id": message.provider_message_id if message else None,
                "error": message.error if message else intent.last_error,
                "sent_at": message.sent_at if message else None,
                "subject": message.subject if message else _text(payload.get("subject")),
                "recipient": message.recipient if message else _text(payload.get("to")),
                "approval_id": intent.approval_id,
                "intent_id": intent.id,
                "attempt_count": intent.attempt_count,
                "queued_at": intent.created_at,
                "attempted_at": attempts[0].started_at if attempts else None,
                "completed_at": message.sent_at if message else None,
                "lead_title": None,
                "company_name": None,
                "attempts": [
                    {
                        "outcome": attempt.outcome.value,
                        "error": attempt.error,
                        "external_id": attempt.external_id,
                        "started_at": attempt.started_at,
                    }
                    for attempt in attempts
                ],
            }
        )
    return result


def _email_state(status: str, approval_status: str | None) -> str:
    if approval_status in {ApprovalStatus.pending.value, ApprovalStatus.approved.value}:
        return (
            "awaiting_approval" if approval_status == ApprovalStatus.pending.value else "approved"
        )
    return {
        IntentStatus.pending.value: "queued",
        IntentStatus.dispatching.value: "sending",
        IntentStatus.succeeded.value: "accepted",
        EmailStatus.sent.value: "accepted",
        IntentStatus.failed.value: "failed",
        IntentStatus.needs_attention.value: "needs_attention",
    }.get(status, status)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _uuid_or_none(value: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


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


def _scoped(model: Any, organization_id: uuid.UUID, scope: DataScope) -> list[Any]:
    filters = [model.organization_id == organization_id]
    clause = scope_clause(model.origin, scope)
    if clause is not None:
        filters.append(clause)
    return filters


def _status_counts(
    db: Session, organization_id: uuid.UUID, scope: DataScope
) -> dict[str, dict[str, int]]:
    rows = db.execute(
        select(WorkflowRun.kind, WorkflowRun.status, func.count())
        .where(*_scoped(WorkflowRun, organization_id, scope))
        .group_by(WorkflowRun.kind, WorkflowRun.status)
    ).all()
    grouped: dict[str, dict[str, int]] = {}
    for kind, status, count in rows:
        grouped.setdefault(kind.value, {})[status.value] = int(count)
    return grouped


def _awaiting_review(db: Session, organization_id: uuid.UUID, scope: DataScope) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Approval)
            .where(
                *_scoped(Approval, organization_id, scope),
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
