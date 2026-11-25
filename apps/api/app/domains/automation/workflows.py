import hashlib
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.automation.models import (
    AttemptOutcome,
    ExecutionAttempt,
    WebhookKey,
    WorkflowDefinition,
    WorkflowKind,
    WorkflowRun,
    WorkflowStatus,
    WorkflowTask,
)
from app.domains.automation.signatures import open_webhook_secret, sign_webhook
from app.domains.billing.service import enforce_limit
from app.domains.crm.models import Contact, Inquiry, Lead
from app.domains.provenance.origin import Origin
from app.integrations.language import get_chat_client
from app.integrations.n8n import post_webhook
from app.integrations.outcomes import DeliveryFailed, OutcomeUncertain

logger = structlog.get_logger(__name__)
_MAX_ATTEMPTS = 2


def stage_lead_created(
    db: Session,
    organization_id: uuid.UUID,
    lead_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
) -> None:
    enforce_limit(db, organization_id, "active_workflows")
    key = hashlib.sha256(f"lead:{lead_id}".encode()).hexdigest()
    existing = db.scalar(select(WorkflowRun).where(WorkflowRun.idempotency_key == key))
    if existing is not None:
        return
    lead = db.get(Lead, lead_id)
    db.add(
        WorkflowRun(
            organization_id=organization_id,
            kind=WorkflowKind.lead_processing,
            status=WorkflowStatus.pending,
            idempotency_key=key,
            lead_id=lead_id,
            agent_run_id=agent_run_id,
            payload={"lead_id": str(lead_id)},
            origin=lead.origin if lead is not None else Origin.unknown,
            attempt_count=0,
        )
    )
    db.flush()
    active_definitions = db.scalars(
        select(WorkflowDefinition).where(
            WorkflowDefinition.organization_id == organization_id,
            WorkflowDefinition.active.is_(True),
            WorkflowDefinition.definition["trigger"].as_string() == "lead_created",
        )
    ).all()
    for definition in active_definitions:
        definition_key = hashlib.sha256(
            f"definition:{definition.id}:lead:{lead_id}".encode()
        ).hexdigest()
        if (
            db.scalar(select(WorkflowRun).where(WorkflowRun.idempotency_key == definition_key))
            is None
        ):
            db.add(
                WorkflowRun(
                    organization_id=organization_id,
                    kind=WorkflowKind.follow_up,
                    status=WorkflowStatus.pending,
                    idempotency_key=definition_key,
                    lead_id=lead_id,
                    agent_run_id=agent_run_id,
                    payload={
                        "lead_id": str(lead_id),
                        "workflow_definition_id": str(definition.id),
                        "definition": definition.definition,
                    },
                    origin=lead.origin if lead is not None else Origin.unknown,
                    attempt_count=0,
                )
            )


def stage_lead_status_changed(
    db: Session,
    organization_id: uuid.UUID,
    lead_id: uuid.UUID,
    previous_status: str,
    new_status: str,
) -> None:
    if previous_status == new_status:
        return
    lead = db.get(Lead, lead_id)
    if lead is None:
        return
    definitions = db.scalars(
        select(WorkflowDefinition).where(
            WorkflowDefinition.organization_id == organization_id,
            WorkflowDefinition.active.is_(True),
            WorkflowDefinition.definition["trigger"].as_string() == "lead_status_changed",
        )
    ).all()
    for definition in definitions:
        key = hashlib.sha256(
            f"definition:{definition.id}:lead:{lead_id}:status:{previous_status}:{new_status}".encode()
        ).hexdigest()
        if db.scalar(select(WorkflowRun).where(WorkflowRun.idempotency_key == key)) is not None:
            continue
        db.add(
            WorkflowRun(
                organization_id=organization_id,
                kind=WorkflowKind.follow_up,
                status=WorkflowStatus.pending,
                idempotency_key=key,
                lead_id=lead_id,
                payload={
                    "lead_id": str(lead_id),
                    "previous_status": previous_status,
                    "new_status": new_status,
                    "workflow_definition_id": str(definition.id),
                    "definition": definition.definition,
                },
                origin=lead.origin,
                attempt_count=0,
            )
        )


def stage_opportunity_changed(
    db: Session,
    organization_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    previous_stage: str,
    new_stage: str,
) -> None:
    if previous_stage == new_stage:
        return
    definitions = db.scalars(
        select(WorkflowDefinition).where(
            WorkflowDefinition.organization_id == organization_id,
            WorkflowDefinition.active.is_(True),
            WorkflowDefinition.definition["trigger"].as_string() == "opportunity_stage_changed",
        )
    ).all()
    for definition in definitions:
        key = hashlib.sha256(
            f"definition:{definition.id}:opportunity:{opportunity_id}:stage:{previous_stage}:{new_stage}".encode()
        ).hexdigest()
        if db.scalar(select(WorkflowRun).where(WorkflowRun.idempotency_key == key)) is not None:
            continue
        db.add(
            WorkflowRun(
                organization_id=organization_id,
                kind=WorkflowKind.follow_up,
                status=WorkflowStatus.pending,
                idempotency_key=key,
                payload={
                    "opportunity_id": str(opportunity_id),
                    "previous_stage": previous_stage,
                    "new_stage": new_stage,
                    "workflow_definition_id": str(definition.id),
                    "definition": definition.definition,
                },
                origin=Origin.unknown,
                attempt_count=0,
            )
        )


def dispatch_pending(db: Session, organization_id: uuid.UUID) -> None:
    run_ids = list(
        db.scalars(
            select(WorkflowRun.id).where(
                WorkflowRun.organization_id == organization_id,
                WorkflowRun.status == WorkflowStatus.pending,
            )
        )
    )
    for run_id in run_ids:
        dispatch_workflow(db, organization_id, run_id)


def dispatch_scheduled(db: Session) -> None:
    now = datetime.now(UTC)
    definitions = db.scalars(
        select(WorkflowDefinition)
        .where(
            WorkflowDefinition.active.is_(True),
            WorkflowDefinition.definition["trigger"].as_string() == "schedule",
            WorkflowDefinition.next_run_at <= now,
        )
        .with_for_update(skip_locked=True)
    ).all()
    for definition in definitions:
        scheduled_at = definition.next_run_at or now
        key = hashlib.sha256(
            f"schedule:{definition.id}:{scheduled_at.isoformat()}".encode()
        ).hexdigest()
        if db.scalar(select(WorkflowRun).where(WorkflowRun.idempotency_key == key)) is None:
            db.add(
                WorkflowRun(
                    organization_id=definition.organization_id,
                    kind=WorkflowKind.follow_up,
                    status=WorkflowStatus.pending,
                    idempotency_key=key,
                    payload={
                        "workflow_definition_id": str(definition.id),
                        "definition": definition.definition,
                    },
                    origin=Origin.operational,
                    attempt_count=0,
                )
            )
        interval = int(definition.definition.get("interval_seconds", 3600))
        definition.last_run_at = now
        definition.next_run_at = now + timedelta(seconds=max(60, min(interval, 31_536_000)))
    if definitions:
        db.commit()


def dispatch_workflow(db: Session, organization_id: uuid.UUID, run_id: uuid.UUID) -> None:
    run = _claim(db, organization_id, run_id)
    if run is None:
        return
    if _execute_local_actions(db, run):
        return
    settings = get_settings()
    key = db.scalar(select(WebhookKey).where(WebhookKey.organization_id == organization_id))
    if not settings.n8n_lead_webhook_url or key is None:
        _finish(db, run.id, WorkflowStatus.not_configured, "n8n_not_configured", None)
        return
    try:
        envelope = _envelope(run, key)
    except AppError:
        _finish(db, run.id, WorkflowStatus.failed, "webhook_key_unreadable", None)
        return
    last_error = "n8n_unreachable"
    for _attempt in range(_MAX_ATTEMPTS):
        attempt = _start_attempt(db, run.id, organization_id)
        try:
            status_code = post_webhook(settings.n8n_lead_webhook_url, envelope)
        except OutcomeUncertain:
            _finish_attempt(db, attempt.id, AttemptOutcome.uncertain, "n8n_timeout", None)
            _finish(db, run.id, WorkflowStatus.needs_attention, "n8n_timeout", None)
            return
        except DeliveryFailed:
            last_error = "n8n_unreachable"
            _finish_attempt(db, attempt.id, AttemptOutcome.failed, last_error, None)
            continue
        if status_code >= 500:
            last_error = f"http_{status_code}"
            _finish_attempt(db, attempt.id, AttemptOutcome.failed, last_error, None)
            continue
        if status_code >= 400:
            _finish_attempt(db, attempt.id, AttemptOutcome.failed, f"http_{status_code}", None)
            _finish(db, run.id, WorkflowStatus.failed, f"http_{status_code}", None)
            return
        _finish_attempt(db, attempt.id, AttemptOutcome.succeeded, None, None)
        _mark_accepted(db, run.id)
        return
    _finish(db, run.id, WorkflowStatus.failed, last_error, None)


def _execute_local_actions(db: Session, run: WorkflowRun) -> bool:
    definition = run.payload.get("definition") if isinstance(run.payload, dict) else None
    actions = definition.get("actions", []) if isinstance(definition, dict) else []
    if not actions:
        return False
    from app.domains.agents.models import AgentRun, RunStatus
    from app.domains.approvals.models import ActionType
    from app.domains.approvals.service import create_approval

    lead = db.get(Lead, run.lead_id) if run.lead_id else None
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = action.get("type")
        if action_type == "create_task":
            if (
                db.scalar(select(WorkflowTask).where(WorkflowTask.workflow_run_id == run.id))
                is None
            ):
                contact_id = lead.contact_id if lead is not None else None
                db.add(
                    WorkflowTask(
                        organization_id=run.organization_id,
                        workflow_run_id=run.id,
                        lead_id=run.lead_id,
                        contact_id=contact_id,
                        assignee_user_id=lead.owner_user_id if lead is not None else None,
                        title=str(action.get("title") or "Workflow follow-up"),
                        description=str(action.get("description"))
                        if action.get("description")
                        else None,
                        status="open",
                    )
                )
        elif action_type == "prepare_follow_up":
            if lead is None or lead.contact_id is None:
                _finish(db, run.id, WorkflowStatus.failed, "follow_up_contact_missing", None)
                return True
            contact = db.get(Contact, lead.contact_id)
            inquiry = db.scalar(
                select(Inquiry).where(
                    Inquiry.organization_id == run.organization_id, Inquiry.lead_id == lead.id
                )
            )
            if contact is None or not contact.email or inquiry is None:
                _finish(db, run.id, WorkflowStatus.failed, "follow_up_recipient_unavailable", None)
                return True
            existing = db.scalar(
                select(AgentRun).where(
                    AgentRun.organization_id == run.organization_id,
                    AgentRun.inquiry_id == inquiry.id,
                    AgentRun.status == RunStatus.awaiting_approval,
                )
            )
            if existing is None:
                try:
                    draft = get_chat_client(db, run.organization_id).complete(
                        "You draft concise customer follow-up emails. "
                        "Return JSON with subject and body only.",
                        f"Lead: {lead.title}\nContact: {contact.full_name}\n"
                        f"Inquiry: {inquiry.subject}\nDetails: {inquiry.body}\n"
                        "Write a factual, helpful follow-up.",
                    )
                    parsed = json.loads(draft)
                    subject = str(parsed.get("subject") or f"Following up on {lead.title}")
                    body = str(
                        parsed.get("body") or "We would be glad to continue the conversation."
                    )
                except (AppError, ValueError, TypeError, json.JSONDecodeError) as exc:
                    _finish(db, run.id, WorkflowStatus.failed, "follow_up_drafting_failed", None)
                    logger.warning(
                        "workflow_follow_up_draft_failed",
                        workflow_run_id=str(run.id),
                        error_code=getattr(exc, "code", "draft_error"),
                    )
                    return True
                agent_run = AgentRun(
                    organization_id=run.organization_id,
                    inquiry_id=inquiry.id,
                    started_by=lead.owner_user_id,
                    status=RunStatus.awaiting_approval,
                    origin=lead.origin,
                )
                db.add(agent_run)
                db.flush()
                create_approval(
                    db,
                    organization_id=run.organization_id,
                    run_id=agent_run.id,
                    requested_by=lead.owner_user_id,
                    action_type=ActionType.prepare_customer_response,
                    payload={
                        "lead_id": str(lead.id),
                        "contact_id": str(contact.id),
                        "recipient": contact.email,
                        "subject": subject,
                        "body": body,
                    },
                    position=0,
                    commit=False,
                )
    run.status = WorkflowStatus.completed
    run.last_error = None
    db.commit()
    return True


def complete_lead_callback(
    db: Session, organization_id: uuid.UUID, workflow_run_id: uuid.UUID, lead_id: uuid.UUID
) -> dict[str, Any]:
    updated = db.execute(
        update(WorkflowRun)
        .where(
            WorkflowRun.id == workflow_run_id,
            WorkflowRun.organization_id == organization_id,
            WorkflowRun.lead_id == lead_id,
            WorkflowRun.status.in_(
                [
                    WorkflowStatus.dispatching,
                    WorkflowStatus.accepted,
                    WorkflowStatus.needs_attention,
                ]
            ),
        )
        .values(status=WorkflowStatus.completed, last_error=None)
    )
    db.commit()
    changed = updated.rowcount if isinstance(updated, CursorResult) else 0
    if changed == 0:
        run = db.get(WorkflowRun, workflow_run_id)
        if run is None or run.organization_id != organization_id:
            return {"status": "ignored"}
        return {"status": run.status.value, "workflow_run_id": str(run.id)}
    logger.info(
        "workflow_completed",
        workflow_run_id=str(workflow_run_id),
        organization_id=str(organization_id),
    )
    return {"status": "completed", "workflow_run_id": str(workflow_run_id)}


def recover_workflows(db: Session) -> None:
    # n8n acknowledges a lead event before its callback. A restart cannot tell whether that
    # callback still arrived, so the run waits for review until a matching callback completes it.
    uncertain = list(
        db.scalars(
            select(WorkflowRun).where(
                WorkflowRun.status.in_([WorkflowStatus.dispatching, WorkflowStatus.accepted])
            )
        )
    )
    for run in uncertain:
        missing_callback = run.status == WorkflowStatus.accepted
        run.status = WorkflowStatus.needs_attention
        run.last_error = "callback_missing" if missing_callback else "execution_uncertain"
    db.commit()
    org_ids = list(
        db.scalars(
            select(WorkflowRun.organization_id).where(WorkflowRun.status == WorkflowStatus.pending)
        ).all()
    )
    for organization_id in set(org_ids):
        try:
            dispatch_pending(db, organization_id)
        except AppError:
            logger.error("workflow_recovery_failed", organization_id=str(organization_id))


def _envelope(run: WorkflowRun, key: WebhookKey) -> dict[str, object]:
    body = json.dumps(
        {
            "lead_id": str(run.lead_id),
            "outcome": "processed",
            "workflow_run_id": str(run.id),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    timestamp = str(int(time.time()))
    secret = open_webhook_secret(key.secret)
    signature = sign_webhook(secret, timestamp, run.idempotency_key, body)
    settings = get_settings()
    return {
        "callback_url": f"{settings.public_api_url.rstrip('/')}/api/v1/hooks/lead-processed",
        "headers": {
            "X-ATLAS-Key-Id": str(key.id),
            "X-ATLAS-Timestamp": timestamp,
            "X-ATLAS-Idempotency-Key": run.idempotency_key,
            "X-ATLAS-Signature": signature,
        },
        "body_text": body.decode(),
    }


def _claim(db: Session, organization_id: uuid.UUID, run_id: uuid.UUID) -> WorkflowRun | None:
    claimed = db.execute(
        update(WorkflowRun)
        .where(
            WorkflowRun.id == run_id,
            WorkflowRun.organization_id == organization_id,
            WorkflowRun.status == WorkflowStatus.pending,
        )
        .values(status=WorkflowStatus.dispatching, attempt_count=WorkflowRun.attempt_count + 1)
        .returning(WorkflowRun.id)
    ).scalar_one_or_none()
    if claimed is None:
        db.rollback()
        return None
    db.commit()
    return db.get(WorkflowRun, run_id)


def _start_attempt(db: Session, run_id: uuid.UUID, organization_id: uuid.UUID) -> ExecutionAttempt:
    run = db.get(WorkflowRun, run_id)
    attempt = ExecutionAttempt(
        organization_id=organization_id,
        workflow_run_id=run_id,
        outcome=AttemptOutcome.started,
        origin=run.origin if run is not None else Origin.unknown,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


def _finish_attempt(
    db: Session,
    attempt_id: uuid.UUID,
    outcome: AttemptOutcome,
    error: str | None,
    external_id: str | None,
) -> None:
    attempt = db.get(ExecutionAttempt, attempt_id)
    if attempt is None:
        return
    attempt.outcome = outcome
    attempt.error = error
    attempt.external_id = external_id
    from datetime import UTC, datetime

    attempt.finished_at = datetime.now(UTC)
    db.commit()


def _finish(
    db: Session,
    run_id: uuid.UUID,
    status: WorkflowStatus,
    error: str | None,
    _external_id: str | None,
) -> None:
    run = db.get(WorkflowRun, run_id)
    if run is None:
        return
    run.status = status
    run.last_error = error
    db.commit()
    from app.domains.observability.tracing import record_operation

    record_operation(
        operation="workflow",
        status=status.value,
        organization_id=run.organization_id,
        workflow_run_id=run.id,
        agent_run_id=run.agent_run_id,
        error_code=error,
    )
    logger.info("workflow_finished", workflow_run_id=str(run_id), status=status.value)


def _mark_accepted(db: Session, run_id: uuid.UUID) -> None:
    db.execute(
        update(WorkflowRun)
        .where(WorkflowRun.id == run_id, WorkflowRun.status == WorkflowStatus.dispatching)
        .values(status=WorkflowStatus.accepted, last_error=None)
    )
    db.commit()
    logger.info("workflow_accepted", workflow_run_id=str(run_id))
