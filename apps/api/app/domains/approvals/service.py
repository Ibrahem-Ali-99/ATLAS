import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.agents.models import AgentRun
from app.domains.approvals.models import ActionType, Approval, ApprovalStatus
from app.domains.crm import service as crm
from app.domains.crm.models import LeadStatus
from app.domains.provenance.origin import Origin


def payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def create_approval(
    db: Session,
    *,
    organization_id: uuid.UUID,
    run_id: uuid.UUID,
    requested_by: uuid.UUID,
    action_type: ActionType,
    payload: dict[str, Any],
    position: int,
    commit: bool = True,
) -> Approval:
    run = db.get(AgentRun, run_id)
    approval = Approval(
        organization_id=organization_id,
        run_id=run_id,
        requested_by=requested_by,
        action_type=action_type,
        position=position,
        payload=payload,
        payload_hash=payload_hash(payload),
        status=ApprovalStatus.pending,
        origin=run.origin if run is not None else Origin.unknown,
        expires_at=datetime.now(UTC) + timedelta(hours=get_settings().approval_ttl_hours),
    )
    db.add(approval)
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(approval)
    return approval


def get_approval(db: Session, organization_id: uuid.UUID, approval_id: uuid.UUID) -> Approval:
    approval = db.scalar(
        select(Approval).where(
            Approval.id == approval_id, Approval.organization_id == organization_id
        )
    )
    if approval is None:
        raise AppError(404, "not_found", "Resource not found")
    return approval


def list_approvals(
    db: Session,
    organization_id: uuid.UUID,
    *,
    status: ApprovalStatus | None,
    run_id: uuid.UUID | None,
    page: int,
    page_size: int,
) -> tuple[list[Approval], int]:
    filters = [Approval.organization_id == organization_id]
    if status is not None:
        filters.append(Approval.status == status)
    if run_id is not None:
        filters.append(Approval.run_id == run_id)
    count = db.scalar(select(func.count()).select_from(Approval).where(*filters)) or 0
    offset = (page - 1) * page_size
    items = list(
        db.scalars(
            select(Approval)
            .where(*filters)
            .order_by(Approval.created_at.desc())
            .offset(offset)
            .limit(page_size)
        ).all()
    )
    return items, count


def list_for_run(db: Session, organization_id: uuid.UUID, run_id: uuid.UUID) -> list[Approval]:
    return list(
        db.scalars(
            select(Approval)
            .where(Approval.organization_id == organization_id, Approval.run_id == run_id)
            .order_by(Approval.position.asc())
        ).all()
    )


def decide(
    db: Session,
    organization_id: uuid.UUID,
    approval_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    *,
    approved: bool,
    note: str | None,
) -> Approval:
    approval = _locked(db, organization_id, approval_id)
    _reject_if_stale(db, approval)
    if approval.status != ApprovalStatus.pending:
        raise AppError(409, "already_decided", "This action has already been decided")
    approval.status = ApprovalStatus.approved if approved else ApprovalStatus.rejected
    approval.decided_by = actor_user_id
    approval.decided_at = datetime.now(UTC)
    approval.decision_note = note
    db.commit()
    db.refresh(approval)
    from app.domains.observability.tracing import record_operation

    record_operation(
        operation="approval_decision",
        status="succeeded" if approved else "rejected",
        organization_id=approval.organization_id,
        agent_run_id=approval.run_id,
        approval_id=approval.id,
    )
    return approval


def execute_approved(
    db: Session, organization_id: uuid.UUID, approval_id: uuid.UUID
) -> dict[str, Any]:
    """Commit a CRM write and its approval completion in one transaction.

    A committed ``executing`` row from an older process is not applied again. The
    business write may already be visible, and this process cannot prove that it is not.
    """

    approval = _locked(db, organization_id, approval_id)
    if approval.status == ApprovalStatus.executed:
        raise AppError(409, "already_executed", "This action was already executed")
    if approval.status == ApprovalStatus.needs_attention:
        raise AppError(409, "needs_attention", "The outcome of this action could not be determined")
    _reject_if_stale(db, approval)
    if approval.status == ApprovalStatus.executing:
        if approval.action_type in _EXTERNAL_ACTIONS:
            from app.domains.automation.intents import resume_intent

            return resume_intent(db, approval)
        approval.status = ApprovalStatus.needs_attention
        approval.execution_error = "execution_uncertain"
        db.commit()
        raise AppError(409, "needs_attention", "The outcome of this action could not be determined")
    if approval.status != ApprovalStatus.approved:
        raise AppError(409, "invalid_transition", "This approval cannot be executed")
    if approval.action_type in _EXTERNAL_ACTIONS:
        return _execute_external(db, approval)
    try:
        result = _apply(db, organization_id, approval)
    except AppError as exc:
        db.rollback()
        failed = _locked(db, organization_id, approval_id)
        failed.status = ApprovalStatus.failed
        failed.execution_error = exc.message[:500]
        db.commit()
        raise
    if approval.action_type == ActionType.create_lead:
        from app.domains.automation.workflows import stage_lead_created

        stage_lead_created(
            db,
            organization_id,
            _uuid_value(result.get("lead_id")),
            approval.run_id,
        )
    approval.status = ApprovalStatus.executed
    approval.execution_result = result
    approval.executed_at = datetime.now(UTC)
    approval.execution_error = None
    db.commit()
    from app.domains.automation.workflows import dispatch_pending

    dispatch_pending(db, organization_id)
    return result


_EXTERNAL_ACTIONS = {ActionType.prepare_customer_response, ActionType.request_appointment}


def _execute_external(db: Session, approval: Approval) -> dict[str, Any]:
    from app.domains.automation.intents import dispatch_intent, stage_intent

    payload = dict(approval.payload)
    payload["lead_id"] = str(_resolve_lead(db, approval, payload))
    intent = stage_intent(db, approval, payload)
    approval.status = ApprovalStatus.executing
    db.commit()
    if approval.action_type == ActionType.prepare_customer_response:
        from app.core.config import get_settings

        if get_settings().environment != "test":
            return {
                "status": "queued",
                "intent_id": str(intent.id),
                "approval_id": str(approval.id),
            }
    return dispatch_intent(db, approval.organization_id, intent.id)


def execute_decisions(
    db: Session, organization_id: uuid.UUID, run_id: uuid.UUID
) -> tuple[int, int, int]:
    rows = list_for_run(db, organization_id, run_id)
    if any(row.status == ApprovalStatus.pending for row in rows):
        raise AppError(
            409,
            "approval_required",
            "An admin has to approve or reject the proposed actions",
        )
    executed = 0
    rejected = 0
    failed = 0
    for row in rows:
        if row.status == ApprovalStatus.rejected:
            rejected += 1
            continue
        if row.status == ApprovalStatus.executed:
            executed += 1
            continue
        if row.status == ApprovalStatus.needs_attention:
            failed += 1
            continue
        if row.status not in {ApprovalStatus.approved, ApprovalStatus.executing}:
            raise AppError(409, "invalid_transition", "This approval cannot be executed")
        try:
            execute_approved(db, organization_id, row.id)
        except AppError as exc:
            if exc.code == "already_executed":
                executed += 1
                continue
            failed += 1
            continue
        executed += 1
    return executed, rejected, failed


def _locked(db: Session, organization_id: uuid.UUID, approval_id: uuid.UUID) -> Approval:
    approval = db.scalar(
        select(Approval)
        .where(Approval.id == approval_id, Approval.organization_id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if approval is None:
        raise AppError(404, "not_found", "Resource not found")
    return approval


def _reject_if_stale(db: Session, approval: Approval) -> None:
    current = approval.payload
    if not isinstance(current, dict) or payload_hash(current) != approval.payload_hash:
        approval.status = ApprovalStatus.failed
        approval.execution_error = "approval_invalid"
        db.commit()
        raise AppError(409, "approval_invalid", "The action payload no longer matches the approval")
    expires_at = approval.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        approval.status = ApprovalStatus.expired
        db.commit()
        raise AppError(409, "approval_expired", "This approval has expired")


def _apply(db: Session, organization_id: uuid.UUID, approval: Approval) -> dict[str, Any]:
    payload = approval.payload
    if approval.action_type == ActionType.create_lead:
        lead = crm.create_lead(
            db,
            organization_id,
            approval.requested_by,
            {**_lead_values(payload), "origin": approval.origin},
            commit=False,
        )
        return {"lead_id": str(lead.id)}
    if approval.action_type == ActionType.update_lead:
        lead = crm.update_lead(
            db,
            organization_id,
            _uuid_value(payload.get("lead_id")),
            _lead_updates(payload),
            commit=False,
        )
        return {"lead_id": str(lead.id)}
    raise AppError(422, "invalid_action", "This action type is not supported")


def _lead_values(payload: Mapping[str, Any]) -> dict[str, object]:
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise AppError(409, "approval_invalid", "The action payload no longer matches the approval")
    values: dict[str, object] = {
        "title": title.strip()[:200],
        "status": _lead_status(payload.get("status")),
        "source": "agent",
        "notes": _notes(payload.get("notes")),
    }
    company_id = payload.get("company_id")
    contact_id = payload.get("contact_id")
    if isinstance(company_id, str) and company_id:
        values["company_id"] = _uuid_value(company_id)
    if isinstance(contact_id, str) and contact_id:
        values["contact_id"] = _uuid_value(contact_id)
    return values


def _lead_updates(payload: Mapping[str, Any]) -> dict[str, object]:
    values: dict[str, object] = {"status": _lead_status(payload.get("status"))}
    notes = payload.get("notes")
    if isinstance(notes, str):
        values["notes"] = notes[:4000]
    return values


def _lead_status(value: object) -> LeadStatus:
    try:
        return LeadStatus(str(value))
    except ValueError as exc:
        raise AppError(
            409, "approval_invalid", "The action payload no longer matches the approval"
        ) from exc


def _notes(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:4000]


def _resolve_lead(db: Session, approval: Approval, payload: Mapping[str, Any]) -> uuid.UUID:
    raw = payload.get("lead_id")
    if isinstance(raw, str) and raw:
        return _uuid_value(raw)
    if payload.get("attach_to") != "run_lead":
        raise AppError(409, "approval_invalid", "The action payload no longer matches the approval")
    sibling = db.scalar(
        select(Approval).where(
            Approval.run_id == approval.run_id,
            Approval.organization_id == approval.organization_id,
            Approval.action_type.in_([ActionType.create_lead, ActionType.update_lead]),
        )
    )
    if (
        sibling is None
        or sibling.status != ApprovalStatus.executed
        or not isinstance(sibling.execution_result, dict)
    ):
        raise AppError(409, "approval_blocked", "The lead action was not approved")
    return _uuid_value(sibling.execution_result.get("lead_id"))


def _uuid_value(value: object) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise AppError(
            409, "approval_invalid", "The action payload no longer matches the approval"
        ) from exc
