import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.agents.models import AgentEvent, AgentRun, RunStatus
from app.domains.approvals.models import ActionType, Approval, ApprovalStatus
from app.domains.automation.models import (
    AttemptOutcome,
    CalendarBooking,
    EmailMessage,
    EmailStatus,
    ExecutionAttempt,
    ExecutionIntent,
    IntentStatus,
)
from app.domains.crm import service as crm
from app.domains.crm.models import Contact, InteractionKind
from app.integrations.calendar import Slot, calendar_adapter
from app.integrations.email import OutboundEmail, normalize_recipient, send_email
from app.integrations.outcomes import DeliveryFailed, OutcomeUncertain

_MAX_ATTEMPTS = 2


def stage_intent(db: Session, approval: Approval, payload: dict[str, Any]) -> ExecutionIntent:
    existing = db.scalar(select(ExecutionIntent).where(ExecutionIntent.approval_id == approval.id))
    if existing is not None:
        return existing
    intent = ExecutionIntent(
        organization_id=approval.organization_id,
        approval_id=approval.id,
        action_type=approval.action_type,
        payload=dict(payload),
        idempotency_key=hashlib.sha256(str(approval.id).encode()).hexdigest(),
        status=IntentStatus.pending,
        origin=approval.origin,
        attempt_count=0,
    )
    db.add(intent)
    db.flush()
    return intent


def dispatch_intent(
    db: Session, organization_id: uuid.UUID, intent_id: uuid.UUID
) -> dict[str, Any]:
    intent = _claim(db, organization_id, intent_id)
    if intent is None:
        return _when_unclaimed(db, organization_id, intent_id)
    attempt = _start_attempt(db, intent)
    action = intent.action_type.value
    try:
        plan = _plan(db, intent)
    except OutcomeUncertain as exc:
        _fail(db, intent.id, attempt.id, AttemptOutcome.uncertain, "outcome_uncertain")
        _trace_adapter(
            organization_id, intent.approval_id, "uncertain", "outcome_uncertain", action
        )
        raise AppError(
            409, "needs_attention", "The external outcome could not be determined"
        ) from exc
    except DeliveryFailed as exc:
        if intent.attempt_count < _MAX_ATTEMPTS:
            _requeue(db, intent.id, attempt.id, "delivery_failed")
            return dispatch_intent(db, organization_id, intent_id)
        _fail(db, intent.id, attempt.id, AttemptOutcome.failed, "delivery_failed")
        _trace_adapter(organization_id, intent.approval_id, "failed", "delivery_failed", action)
        raise AppError(
            502, "delivery_failed", "The external service did not accept the action"
        ) from exc
    except AppError as exc:
        _fail(db, intent.id, attempt.id, AttemptOutcome.failed, exc.message[:500])
        _trace_adapter(organization_id, intent.approval_id, "failed", exc.code, action)
        raise
    result = _succeed(db, intent.id, attempt.id, plan)
    _trace_adapter(organization_id, intent.approval_id, "succeeded", None, action)
    return result


def resume_intent(db: Session, approval: Approval) -> dict[str, Any]:
    intent = db.scalar(select(ExecutionIntent).where(ExecutionIntent.approval_id == approval.id))
    if intent is None or intent.status == IntentStatus.dispatching:
        _mark_approval(db, approval.id, ApprovalStatus.needs_attention, "execution_uncertain", None)
        raise AppError(409, "needs_attention", "The outcome of this action could not be determined")
    if intent.status == IntentStatus.pending:
        return dispatch_intent(db, approval.organization_id, intent.id)
    if intent.status == IntentStatus.succeeded and isinstance(intent.result, dict):
        _mark_approval(db, approval.id, ApprovalStatus.executed, None, intent.result)
        return intent.result
    if intent.status == IntentStatus.needs_attention:
        _mark_approval(db, approval.id, ApprovalStatus.needs_attention, "execution_uncertain", None)
        raise AppError(409, "needs_attention", "The outcome of this action could not be determined")
    _mark_approval(
        db, approval.id, ApprovalStatus.failed, intent.last_error or "delivery_failed", None
    )
    raise AppError(409, "execution_failed", "This action could not be completed")


def recover_intents(db: Session) -> None:
    """Finish interrupted external work without repeating an uncertain send."""

    rows = list(
        db.scalars(
            select(ExecutionIntent).where(ExecutionIntent.status == IntentStatus.dispatching)
        )
    )
    for intent in rows:
        if intent.action_type == ActionType.request_appointment:
            booking = db.scalar(
                select(CalendarBooking).where(CalendarBooking.intent_id == intent.id)
            )
            if booking is not None:
                result = {
                    "lead_id": str(booking.lead_id),
                    "booking_id": str(booking.id),
                    "provider": booking.provider,
                }
                intent.status = IntentStatus.succeeded
                intent.result = result
                intent.external_id = str(booking.id)
                _mark_approval(db, intent.approval_id, ApprovalStatus.executed, None, result)
                continue
            intent.status = IntentStatus.pending
            continue
        email = db.scalar(select(EmailMessage).where(EmailMessage.intent_id == intent.id))
        if email is not None and email.status == EmailStatus.sent:
            result = {
                "lead_id": str(email.lead_id) if email.lead_id else "",
                "email_id": str(email.id),
                "message_id": email.provider_message_id or "",
                "email_mode": email.mode,
            }
            intent.status = IntentStatus.succeeded
            intent.result = result
            intent.external_id = email.provider_message_id
            _mark_approval(db, intent.approval_id, ApprovalStatus.executed, None, result)
            continue
        intent.status = IntentStatus.needs_attention
        intent.last_error = "execution_uncertain"
        _mark_approval(
            db, intent.approval_id, ApprovalStatus.needs_attention, "execution_uncertain", None
        )
    db.commit()
    pending = db.execute(
        select(ExecutionIntent.id, ExecutionIntent.organization_id).where(
            ExecutionIntent.status == IntentStatus.pending
        )
    ).all()
    for intent_id, organization_id in pending:
        try:
            dispatch_intent(db, organization_id, intent_id)
        except AppError:
            continue


def _claim(db: Session, organization_id: uuid.UUID, intent_id: uuid.UUID) -> ExecutionIntent | None:
    claimed = db.execute(
        update(ExecutionIntent)
        .where(
            ExecutionIntent.id == intent_id,
            ExecutionIntent.organization_id == organization_id,
            ExecutionIntent.status == IntentStatus.pending,
        )
        .values(status=IntentStatus.dispatching, attempt_count=ExecutionIntent.attempt_count + 1)
        .returning(ExecutionIntent.id)
    ).scalar_one_or_none()
    if claimed is None:
        db.rollback()
        return None
    db.commit()
    intent = db.get(ExecutionIntent, intent_id)
    if intent is None or intent.organization_id != organization_id:
        return None
    return intent


def _when_unclaimed(
    db: Session, organization_id: uuid.UUID, intent_id: uuid.UUID
) -> dict[str, Any]:
    intent = db.get(ExecutionIntent, intent_id)
    if intent is None or intent.organization_id != organization_id:
        raise AppError(404, "not_found", "Resource not found")
    if intent.status == IntentStatus.succeeded and isinstance(intent.result, dict):
        return intent.result
    if intent.status == IntentStatus.dispatching:
        raise AppError(409, "already_executing", "This action is already being executed")
    if intent.status == IntentStatus.needs_attention:
        raise AppError(409, "needs_attention", "The outcome of this action could not be determined")
    raise AppError(409, "execution_failed", "This action could not be completed")


def _start_attempt(db: Session, intent: ExecutionIntent) -> ExecutionAttempt:
    attempt = ExecutionAttempt(
        organization_id=intent.organization_id,
        intent_id=intent.id,
        outcome=AttemptOutcome.started,
        origin=intent.origin,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


def _plan(db: Session, intent: ExecutionIntent) -> dict[str, Any]:
    payload = intent.payload if isinstance(intent.payload, dict) else {}
    lead_id = _uuid(payload.get("lead_id"))
    body = payload.get("body")
    if not isinstance(body, str) or not body.strip():
        raise AppError(409, "approval_invalid", "The action payload no longer matches the approval")
    if intent.action_type == ActionType.prepare_customer_response:
        recipient = payload.get("to")
        if not isinstance(recipient, str):
            raise AppError(422, "invalid_recipient", "The approved action has no recipient")
        contact_id = _uuid(payload.get("contact_id"))
        snapshot = payload.get("recipient_snapshot")
        if contact_id is not None:
            contact = db.scalar(
                select(Contact).where(
                    Contact.id == contact_id,
                    Contact.organization_id == intent.organization_id,
                )
            )
            if contact is None or not contact.email:
                raise AppError(
                    422,
                    "invalid_recipient",
                    "The approved recipient is not an organization contact",
                )
            if not isinstance(snapshot, str) or normalize_recipient(
                snapshot
            ) != normalize_recipient(contact.email):
                raise AppError(
                    409,
                    "recipient_changed",
                    "The approved recipient changed; review the action again",
                )
            if normalize_recipient(recipient) != normalize_recipient(snapshot):
                raise AppError(
                    409,
                    "recipient_changed",
                    "The approved recipient changed; review the action again",
                )
            recipient = contact.email
        subject = payload.get("subject")
        receipt = send_email(
            OutboundEmail(
                recipient=recipient,
                subject=subject.strip()[:200]
                if isinstance(subject, str) and subject.strip()
                else "Message",
                body=body.strip()[:4000],
                idempotency_key=intent.idempotency_key,
            ),
            db=db,
            organization_id=intent.organization_id,
        )
        return {
            "kind": "email",
            "lead_id": str(lead_id),
            "recipient": recipient.strip(),
            "subject": subject.strip()[:200]
            if isinstance(subject, str) and subject.strip()
            else "Message",
            "body": body.strip()[:4000],
            "message_id": receipt.message_id,
            "email_mode": receipt.mode,
        }
    if intent.action_type == ActionType.request_appointment:
        starts_at = _time(payload.get("starts_at"))
        ends_at = _time(payload.get("ends_at"))
        if ends_at <= starts_at:
            raise AppError(409, "approval_invalid", "The appointment time is not valid")
        return {
            "kind": "calendar",
            "lead_id": str(lead_id),
            "body": body.strip()[:4000],
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
        }
    raise AppError(422, "invalid_action", "This action type is not supported")


def _fail(
    db: Session,
    intent_id: uuid.UUID,
    attempt_id: uuid.UUID,
    outcome: AttemptOutcome,
    error: str,
) -> None:
    db.rollback()
    intent = db.get(ExecutionIntent, intent_id)
    attempt = db.get(ExecutionAttempt, attempt_id)
    if intent is None or attempt is None:
        return
    attempt.outcome = outcome
    attempt.error = error
    attempt.finished_at = _now()
    uncertain = outcome == AttemptOutcome.uncertain
    intent.status = IntentStatus.needs_attention if uncertain else IntentStatus.failed
    intent.last_error = error
    _mark_approval(
        db,
        intent.approval_id,
        ApprovalStatus.needs_attention if uncertain else ApprovalStatus.failed,
        error,
        None,
    )
    _record_failure_side_effect(db, intent, error)
    db.commit()


def _succeed(
    db: Session, intent_id: uuid.UUID, attempt_id: uuid.UUID, plan: dict[str, Any]
) -> dict[str, Any]:
    db.rollback()
    intent = db.get(ExecutionIntent, intent_id)
    attempt = db.get(ExecutionAttempt, attempt_id)
    if intent is None or attempt is None:
        raise AppError(404, "not_found", "Resource not found")
    try:
        result = _record_success(db, intent, plan)
    except AppError as exc:
        if plan.get("kind") == "email":
            _fail(db, intent_id, attempt_id, AttemptOutcome.uncertain, "outcome_uncertain")
            raise AppError(
                409, "needs_attention", "The external outcome could not be determined"
            ) from exc
        _fail(db, intent_id, attempt_id, AttemptOutcome.failed, exc.message[:500])
        raise
    attempt.outcome = AttemptOutcome.succeeded
    attempt.finished_at = _now()
    attempt.external_id = intent.external_id
    intent.status = IntentStatus.succeeded
    intent.result = result
    intent.last_error = None
    _mark_approval(db, intent.approval_id, ApprovalStatus.executed, None, result)
    _event(db, intent, "succeeded", result)
    db.commit()
    return result


def _requeue(db: Session, intent_id: uuid.UUID, attempt_id: uuid.UUID, error: str) -> None:
    db.rollback()
    intent = db.get(ExecutionIntent, intent_id)
    attempt = db.get(ExecutionAttempt, attempt_id)
    if intent is None or attempt is None:
        return
    attempt.outcome = AttemptOutcome.failed
    attempt.error = error
    attempt.finished_at = _now()
    intent.status = IntentStatus.pending
    intent.last_error = error
    db.commit()


def _record_success(db: Session, intent: ExecutionIntent, plan: dict[str, Any]) -> dict[str, Any]:
    approval = db.get(Approval, intent.approval_id)
    if approval is None:
        raise AppError(404, "not_found", "Resource not found")
    lead_id = uuid.UUID(str(plan["lead_id"]))
    author = approval.decided_by or approval.requested_by
    if plan["kind"] == "email":
        interaction = crm.add_interaction(
            db,
            intent.organization_id,
            lead_id,
            author,
            {"kind": InteractionKind.email, "body": plan["body"], "origin": intent.origin},
            commit=False,
        )
        email = EmailMessage(
            organization_id=intent.organization_id,
            lead_id=lead_id,
            intent_id=intent.id,
            recipient=str(plan["recipient"]),
            subject=str(plan["subject"]),
            body=str(plan["body"]),
            status=EmailStatus.sent,
            mode=str(plan["email_mode"]),
            provider_message_id=str(plan["message_id"]),
            origin=intent.origin,
            sent_at=_now(),
        )
        db.add(email)
        db.flush()
        intent.external_id = str(plan["message_id"])
        return {
            "lead_id": str(lead_id),
            "interaction_id": str(interaction.id),
            "email_id": str(email.id),
            "message_id": str(plan["message_id"]),
            "email_mode": str(plan["email_mode"]),
        }
    starts_at = _time(plan.get("starts_at"))
    ends_at = _time(plan.get("ends_at"))
    booking = calendar_adapter().book(
        db,
        Slot(
            organization_id=intent.organization_id,
            lead_id=lead_id,
            intent_id=intent.id,
            starts_at=starts_at,
            ends_at=ends_at,
            origin=intent.origin,
        ),
    )
    interaction = crm.add_interaction(
        db,
        intent.organization_id,
        lead_id,
        author,
        {"kind": InteractionKind.call, "body": plan["body"], "origin": intent.origin},
        commit=False,
    )
    intent.external_id = str(booking.id)
    return {
        "lead_id": str(lead_id),
        "interaction_id": str(interaction.id),
        "booking_id": str(booking.id),
        "provider": booking.provider,
    }


def _record_failure_side_effect(db: Session, intent: ExecutionIntent, error: str | None) -> None:
    if intent.action_type != ActionType.prepare_customer_response:
        return
    if db.scalar(select(EmailMessage.id).where(EmailMessage.intent_id == intent.id)):
        return
    payload = intent.payload if isinstance(intent.payload, dict) else {}
    recipient = payload.get("to")
    lead_raw = payload.get("lead_id")
    lead_id = _uuid(lead_raw) if isinstance(lead_raw, str) else None
    db.add(
        EmailMessage(
            organization_id=intent.organization_id,
            lead_id=lead_id,
            intent_id=intent.id,
            recipient=recipient.strip()[:320] if isinstance(recipient, str) else "unknown",
            subject="Message",
            body="",
            status=(
                EmailStatus.needs_attention
                if intent.status == IntentStatus.needs_attention
                else EmailStatus.failed
            ),
            mode="sandbox",
            origin=intent.origin,
            error=error,
        )
    )


def _mark_approval(
    db: Session,
    approval_id: uuid.UUID,
    status: ApprovalStatus,
    error: str | None,
    result: dict[str, Any] | None,
) -> None:
    approval = db.get(Approval, approval_id)
    if approval is None:
        return
    approval.status = status
    approval.execution_error = error[:500] if error else None
    if result is not None:
        approval.execution_result = result
        approval.executed_at = _now()
        approval.execution_error = None
    _settle_run(db, approval)


def _settle_run(db: Session, approval: Approval) -> None:
    run = db.get(AgentRun, approval.run_id)
    if run is None or run.status != RunStatus.awaiting_approval:
        return
    rows = list(db.scalars(select(Approval).where(Approval.run_id == run.id)))
    if any(
        row.status in {ApprovalStatus.pending, ApprovalStatus.approved, ApprovalStatus.executing}
        for row in rows
    ):
        return
    if any(row.status in {ApprovalStatus.failed, ApprovalStatus.needs_attention} for row in rows):
        run.status = RunStatus.failed
        run.error_code = "execution_failed"
        run.finished_at = _now()
        return
    run.status = RunStatus.completed
    run.finished_at = _now()


def _event(db: Session, intent: ExecutionIntent, status: str, detail: dict[str, Any]) -> None:
    approval = db.get(Approval, intent.approval_id)
    if approval is None:
        return
    db.add(
        AgentEvent(
            organization_id=intent.organization_id,
            run_id=approval.run_id,
            step="external_effect",
            status=status,
            detail={"approval_id": str(approval.id), **detail},
        )
    )


def _uuid(value: object) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise AppError(
            409, "approval_invalid", "The action payload no longer matches the approval"
        ) from exc


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise AppError(409, "approval_invalid", "The appointment time is not valid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AppError(409, "approval_invalid", "The appointment time is not valid") from exc
    if parsed.tzinfo is None:
        raise AppError(409, "approval_invalid", "The appointment time is not valid")
    return parsed


def _now() -> datetime:
    return datetime.now(UTC)


def _trace_adapter(
    organization_id: uuid.UUID,
    approval_id: uuid.UUID,
    status: str,
    error_code: str | None,
    action: str,
) -> None:
    from app.domains.observability.tracing import record_operation

    record_operation(
        operation="external_adapter",
        status=status,
        organization_id=organization_id,
        approval_id=approval_id,
        error_code=error_code,
        detail={"action": action},
    )
