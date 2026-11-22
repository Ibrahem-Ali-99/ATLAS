import hashlib
import json
import time
import uuid
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
    WorkflowKind,
    WorkflowRun,
    WorkflowStatus,
)
from app.domains.automation.signatures import sign_webhook
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
    key = hashlib.sha256(f"lead:{lead_id}".encode()).hexdigest()
    existing = db.scalar(select(WorkflowRun).where(WorkflowRun.idempotency_key == key))
    if existing is not None:
        return
    db.add(
        WorkflowRun(
            organization_id=organization_id,
            kind=WorkflowKind.lead_processing,
            status=WorkflowStatus.pending,
            idempotency_key=key,
            lead_id=lead_id,
            agent_run_id=agent_run_id,
            payload={"lead_id": str(lead_id)},
            attempt_count=0,
        )
    )
    db.flush()


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


def dispatch_workflow(db: Session, organization_id: uuid.UUID, run_id: uuid.UUID) -> None:
    run = _claim(db, organization_id, run_id)
    if run is None:
        return
    settings = get_settings()
    key = db.scalar(select(WebhookKey).where(WebhookKey.organization_id == organization_id))
    if not settings.n8n_lead_webhook_url or key is None:
        _finish(db, run.id, WorkflowStatus.not_configured, "n8n_not_configured", None)
        return
    envelope = _envelope(run, key)
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


def complete_lead_callback(
    db: Session, organization_id: uuid.UUID, workflow_run_id: uuid.UUID, lead_id: uuid.UUID
) -> dict[str, Any]:
    updated = db.execute(
        update(WorkflowRun)
        .where(
            WorkflowRun.id == workflow_run_id,
            WorkflowRun.organization_id == organization_id,
            WorkflowRun.lead_id == lead_id,
            WorkflowRun.status.in_([WorkflowStatus.dispatching, WorkflowStatus.accepted]),
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
    stuck = list(
        db.scalars(select(WorkflowRun).where(WorkflowRun.status == WorkflowStatus.dispatching))
    )
    for run in stuck:
        run.status = WorkflowStatus.needs_attention
        run.last_error = "execution_uncertain"
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
    signature = sign_webhook(key.secret, timestamp, run.idempotency_key, body)
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
    attempt = ExecutionAttempt(
        organization_id=organization_id,
        workflow_run_id=run_id,
        outcome=AttemptOutcome.started,
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
    logger.info("workflow_finished", workflow_run_id=str(run_id), status=status.value)


def _mark_accepted(db: Session, run_id: uuid.UUID) -> None:
    db.execute(
        update(WorkflowRun)
        .where(WorkflowRun.id == run_id, WorkflowRun.status == WorkflowStatus.dispatching)
        .values(status=WorkflowStatus.accepted, last_error=None)
    )
    db.commit()
    logger.info("workflow_accepted", workflow_run_id=str(run_id))
