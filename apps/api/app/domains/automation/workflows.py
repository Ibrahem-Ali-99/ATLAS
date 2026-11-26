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
from app.domains.crm.models import Contact, Inquiry, Lead, LeadStatus, Opportunity
from app.domains.demo.access import organization_is_visitor
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
                        "new_status": lead.status.value if lead is not None else None,
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
    transition_id = uuid.uuid4()
    for definition in definitions:
        key = hashlib.sha256(
            f"definition:{definition.id}:lead-status:{transition_id}".encode()
        ).hexdigest()
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
    transition_id = uuid.uuid4()
    for definition in definitions:
        key = hashlib.sha256(
            f"definition:{definition.id}:opportunity-stage:{transition_id}".encode()
        ).hexdigest()
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
    if organization_is_visitor(db, organization_id):
        run.status = WorkflowStatus.completed
        run.last_error = None
        run.payload = {
            **run.payload,
            "outcome": "simulated",
            "steps": [{"type": "external_dispatch", "status": "simulated"}],
        }
        db.commit()
        return
    if run.payload.get("dry_run"):
        run.status = WorkflowStatus.completed
        run.last_error = None
        run.payload = {
            **run.payload,
            "outcome": "simulated",
            "steps": [{"type": "external_dispatch", "status": "simulated"}],
        }
        db.commit()
        return
    settings = get_settings()
    key = db.scalar(
        select(WebhookKey).where(
            WebhookKey.organization_id == organization_id, WebhookKey.revoked_at.is_(None)
        )
    )
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
    definition = run.payload.get("definition")
    if not isinstance(definition, dict):
        return False
    actions = definition.get("actions", [])
    if not actions:
        return False
    from app.domains.agents.models import AgentRun, RunStatus
    from app.domains.approvals.models import ActionType
    from app.domains.approvals.service import create_approval
    from app.domains.audit.service import record_event
    from app.domains.crm.service import update_lead

    run_id = run.id
    organization_id = run.organization_id
    steps: list[dict[str, str]] = []
    simulated = bool(run.payload.get("dry_run"))
    current_action = "load_context"
    lead = (
        db.scalar(
            select(Lead).where(
                Lead.id == run.lead_id,
                Lead.organization_id == organization_id,
                Lead.archived_at.is_(None),
            )
        )
        if run.lead_id
        else None
    )

    def fail(code: str) -> bool:
        db.rollback()
        run.payload = {
            **run.payload,
            "steps": [
                *(
                    {**step, "status": "rolled_back"} if step["status"] == "completed" else step
                    for step in steps
                ),
                {"type": current_action, "status": "failed"},
            ],
        }
        run.status = WorkflowStatus.failed
        run.last_error = code
        db.commit()
        return True

    opportunity = None
    opportunity_id = run.payload.get("opportunity_id")
    if isinstance(opportunity_id, str):
        try:
            parsed_id = uuid.UUID(opportunity_id)
        except ValueError:
            return fail("workflow_opportunity_invalid")
        opportunity = db.scalar(
            select(Opportunity).where(
                Opportunity.id == parsed_id,
                Opportunity.organization_id == organization_id,
                Opportunity.archived_at.is_(None),
            )
        )
        if opportunity is None:
            return fail("workflow_opportunity_missing")

    trigger = definition.get("trigger")
    if trigger in {"lead_created", "lead_status_changed"} and lead is None:
        return fail("workflow_lead_missing")
    results = []
    conditions = definition.get("conditions", [])
    for condition in conditions:
        value = (
            run.payload.get("new_status") or (lead.status.value if lead is not None else None)
            if condition["field"] == "lead_status"
            else run.payload.get("new_stage")
        )
        passes = value is not None and (
            (value == condition["value"]) == (condition["operator"] == "equals")
        )
        results.append(passes)
        steps.append({"type": "condition", "status": "matched" if passes else "not_matched"})
    if conditions:
        matches = any(results) if definition.get("condition_mode") == "any" else all(results)
        path = run.payload.get("branch") or ("matched" if matches else "otherwise")
        run.payload = {**run.payload, "branch": path}
        steps.append({"type": "branch", "status": path})
        actions = actions if path == "matched" else definition.get("otherwise_actions", [])
        if not actions:
            run.payload = {**run.payload, "steps": steps, "outcome": "skipped"}
            run.status = WorkflowStatus.completed
            db.commit()
            return True

    approval_id = None
    for action in actions:
        if not isinstance(action, dict):
            return fail("invalid_workflow_action")
        action_type = action.get("type")
        current_action = str(action_type)
        if action_type == "require_approval":
            if simulated:
                steps.append({"type": "require_approval", "status": "simulated"})
                continue
            if run.payload.get("review", {}).get("decision") != "approve":
                steps.append({"type": "require_approval", "status": "awaiting_approval"})
                run.payload = {
                    **run.payload,
                    "steps": steps,
                    "outcome": "awaiting_approval",
                    "review_note": action.get("note"),
                }
                run.status = WorkflowStatus.accepted
                db.commit()
                return True
        elif action_type == "update_lead":
            if lead is None:
                return fail("workflow_lead_missing")
            target_status = action.get("status")
            if not isinstance(target_status, str):
                return fail("workflow_lead_status_invalid")
            try:
                status = LeadStatus(target_status)
            except ValueError:
                return fail("workflow_lead_status_invalid")
            if simulated:
                steps.append({"type": "update_lead", "status": "simulated"})
                continue
            try:
                previous = lead.status
                update_lead(db, organization_id, lead.id, {"status": status}, commit=False)
            except AppError as exc:
                return fail(exc.code)
            if previous != status:
                record_event(
                    db,
                    organization_id,
                    "workflow_lead_updated",
                    {
                        "workflow_run_id": str(run_id),
                        "lead_id": str(lead.id),
                        "previous_status": previous.value,
                        "status": status.value,
                    },
                )
        elif action_type == "create_task":
            title = action.get("title", "Workflow follow-up")
            if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
                return fail("workflow_task_title_invalid")
            priority = action.get("priority", "normal")
            due_hours = action.get("due_in_hours")
            if priority not in ("low", "normal", "high", "urgent") or (
                due_hours is not None and (type(due_hours) is not int or not 1 <= due_hours <= 8760)
            ):
                return fail("workflow_task_configuration_invalid")
            if simulated:
                steps.append({"type": "create_task", "status": "simulated"})
                continue
            db.add(
                WorkflowTask(
                    organization_id=organization_id,
                    workflow_run_id=run_id,
                    lead_id=lead.id if lead is not None else None,
                    contact_id=lead.contact_id if lead is not None else None,
                    assignee_user_id=lead.owner_user_id if lead is not None else None,
                    title=title.strip(),
                    description=str(action["description"]) if action.get("description") else None,
                    status="open",
                    priority=priority,
                    due_at=datetime.now(UTC) + timedelta(hours=due_hours) if due_hours else None,
                    opportunity_id=opportunity.id if opportunity is not None else None,
                )
            )
        elif action_type == "prepare_follow_up":
            if lead is None or lead.contact_id is None:
                return fail("follow_up_contact_missing")
            contact = db.scalar(
                select(Contact).where(
                    Contact.id == lead.contact_id,
                    Contact.organization_id == organization_id,
                    Contact.archived_at.is_(None),
                )
            )
            inquiry = db.scalar(
                select(Inquiry)
                .where(Inquiry.organization_id == run.organization_id, Inquiry.lead_id == lead.id)
                .order_by(Inquiry.created_at.desc(), Inquiry.id.desc())
                .limit(1)
            )
            if contact is None or not contact.email or inquiry is None:
                return fail("follow_up_recipient_unavailable")
            if simulated:
                steps.append({"type": "prepare_follow_up", "status": "simulated"})
                continue
            if approval_id is None:
                try:
                    draft = get_chat_client(db, run.organization_id).complete(
                        "You draft concise customer follow-up emails. "
                        "Return JSON with subject and body only.",
                        f"Lead: {lead.title}\nContact: {contact.full_name}\n"
                        f"Inquiry: {inquiry.subject}\nDetails: {inquiry.body}\n"
                        "Write a factual, helpful follow-up.",
                    )
                    parsed = json.loads(draft)
                    if not isinstance(parsed, dict):
                        raise ValueError("Expected a follow-up draft object")
                    subject = str(parsed.get("subject") or f"Following up on {lead.title}")
                    body = str(
                        parsed.get("body") or "We would be glad to continue the conversation."
                    )
                except (AppError, ValueError, TypeError, json.JSONDecodeError) as exc:
                    logger.warning(
                        "workflow_follow_up_draft_failed",
                        workflow_run_id=str(run_id),
                        error_code=getattr(exc, "code", "draft_error"),
                    )
                    return fail("follow_up_drafting_failed")
                agent_run = AgentRun(
                    organization_id=run.organization_id,
                    inquiry_id=inquiry.id,
                    started_by=lead.owner_user_id,
                    status=RunStatus.awaiting_approval,
                    origin=lead.origin,
                )
                db.add(agent_run)
                db.flush()
                approval = create_approval(
                    db,
                    organization_id=run.organization_id,
                    run_id=agent_run.id,
                    requested_by=lead.owner_user_id,
                    action_type=ActionType.prepare_customer_response,
                    payload={
                        "lead_id": str(lead.id),
                        "contact_id": str(contact.id),
                        "to": contact.email,
                        "recipient_snapshot": contact.email,
                        "subject": subject,
                        "body": body,
                    },
                    position=0,
                    commit=False,
                )
                approval_id = str(approval.id)
        else:
            return fail("invalid_workflow_action")
        steps.append({"type": current_action, "status": "completed"})
    payload = {**run.payload, "steps": steps, "approval_id": approval_id}
    if simulated:
        payload["outcome"] = "simulated"
    run.payload = payload
    run.status = WorkflowStatus.completed
    run.last_error = None
    db.commit()
    return True


def complete_lead_callback(
    db: Session,
    organization_id: uuid.UUID,
    workflow_run_id: uuid.UUID,
    lead_id: uuid.UUID,
    *,
    commit: bool = True,
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
    if commit:
        db.commit()
    changed = updated.rowcount if isinstance(updated, CursorResult) else 0
    if changed == 0:
        run = db.get(WorkflowRun, workflow_run_id)
        if run is None or run.organization_id != organization_id or run.lead_id != lead_id:
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
        if run.payload.get("outcome") == "awaiting_approval":
            continue
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
