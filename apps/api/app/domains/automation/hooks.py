import json
import re
import time
import uuid
from typing import Any

import structlog
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.agents.models import AgentEvent, AgentRun, RunStatus
from app.domains.approvals.models import ActionType
from app.domains.approvals.service import create_approval
from app.domains.automation.models import WebhookEvent, WebhookKey
from app.domains.automation.signatures import sign_webhook, signatures_match
from app.domains.automation.workflows import complete_lead_callback
from app.domains.crm import service as crm
from app.domains.crm.models import Inquiry, Lead, LeadStatus
from app.domains.identity.models import Membership, MembershipRole

logger = structlog.get_logger(__name__)
_IDEMPOTENCY = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_calls: dict[str, list[float]] = {}


class LeadCallback(BaseModel):
    workflow_run_id: uuid.UUID
    lead_id: uuid.UUID
    outcome: str = Field(min_length=1, max_length=40)
    organization_id: uuid.UUID | None = None


class FollowUpQuery(BaseModel):
    organization_id: uuid.UUID | None = None


class FollowUpRequest(BaseModel):
    lead_id: uuid.UUID
    body: str = Field(min_length=1, max_length=4000)
    organization_id: uuid.UUID | None = None


def create_webhook_key(db: Session, organization_id: uuid.UUID) -> tuple[WebhookKey, str]:
    import secrets

    existing = db.scalar(select(WebhookKey).where(WebhookKey.organization_id == organization_id))
    if existing is not None:
        raise AppError(409, "already_exists", "This organization already has a webhook key")
    secret = secrets.token_urlsafe(32)
    key = WebhookKey(organization_id=organization_id, name="n8n", secret=secret)
    db.add(key)
    db.commit()
    db.refresh(key)
    return key, secret


def accept_lead_processed(db: Session, headers: Any, body: bytes) -> tuple[int, dict[str, Any]]:
    return _accept(db, headers, body, "lead_processed", LeadCallback, _lead_processed)


def accept_follow_ups(db: Session, headers: Any, body: bytes) -> tuple[int, dict[str, Any]]:
    return _accept(db, headers, body, "follow_ups", FollowUpQuery, _follow_ups)


def accept_follow_up_request(db: Session, headers: Any, body: bytes) -> tuple[int, dict[str, Any]]:
    return _accept(db, headers, body, "follow_up_request", FollowUpRequest, _request_follow_up)


def _accept(
    db: Session,
    headers: Any,
    body: bytes,
    event_type: str,
    model: type[BaseModel],
    handler: Any,
) -> tuple[int, dict[str, Any]]:
    settings = get_settings()
    if len(body) > settings.webhook_max_bytes:
        raise AppError(413, "payload_too_large", "Webhook payload is too large")
    key, idempotency_key = _authenticated(db, headers, body)
    if _limited(str(key.id)):
        raise AppError(429, "rate_limited", "Too many webhook requests")
    existing = db.scalar(
        select(WebhookEvent).where(
            WebhookEvent.key_id == key.id,
            WebhookEvent.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        logger.info("webhook_replay", key_id=str(key.id), event_type=event_type)
        return existing.response_code, dict(existing.response_body)
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError as exc:
        raise AppError(422, "invalid_payload", "Webhook payload must be a JSON object") from exc
    if not isinstance(payload, dict):
        raise AppError(422, "invalid_payload", "Webhook payload must be a JSON object")
    try:
        parsed = model.model_validate(payload)
    except ValidationError as exc:
        raise AppError(422, "invalid_payload", "Webhook payload must be a JSON object") from exc
    _reject_foreign_organization(parsed, key.organization_id)
    try:
        response = handler(db, key.organization_id, parsed)
    except AppError:
        db.rollback()
        raise
    event = WebhookEvent(
        organization_id=key.organization_id,
        key_id=key.id,
        idempotency_key=idempotency_key,
        event_type=event_type,
        payload=payload,
        response_code=200,
        response_body=response,
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        stored = db.scalar(
            select(WebhookEvent).where(
                WebhookEvent.key_id == key.id,
                WebhookEvent.idempotency_key == idempotency_key,
            )
        )
        if stored is None:
            raise
        return stored.response_code, dict(stored.response_body)
    logger.info(
        "webhook_accepted",
        key_id=str(key.id),
        organization_id=str(key.organization_id),
        event_type=event_type,
    )
    return 200, response


def _authenticated(db: Session, headers: Any, body: bytes) -> tuple[WebhookKey, str]:
    key_id = _header(headers, "x-atlas-key-id")
    timestamp = _header(headers, "x-atlas-timestamp")
    idempotency_key = _header(headers, "x-atlas-idempotency-key")
    signature = _header(headers, "x-atlas-signature")
    if not key_id or not timestamp or not idempotency_key or not signature:
        raise AppError(401, "webhook_unauthorized", "Webhook authentication failed")
    if _IDEMPOTENCY.fullmatch(idempotency_key) is None or not timestamp.isdigit():
        raise AppError(401, "webhook_unauthorized", "Webhook authentication failed")
    try:
        parsed_id = uuid.UUID(key_id)
    except ValueError as exc:
        raise AppError(401, "webhook_unauthorized", "Webhook authentication failed") from exc
    key = db.get(WebhookKey, parsed_id)
    expected = "" if key is None else sign_webhook(key.secret, timestamp, idempotency_key, body)
    if key is None or not signatures_match(expected, signature):
        raise AppError(401, "webhook_unauthorized", "Webhook authentication failed")
    skew = abs(int(time.time()) - int(timestamp))
    if skew > get_settings().webhook_skew_seconds:
        raise AppError(401, "webhook_expired", "Webhook timestamp is outside the allowed window")
    return key, idempotency_key


def _header(headers: Any, name: str) -> str:
    value = headers.get(name)
    return value.strip() if isinstance(value, str) else ""


def _limited(key_id: str) -> bool:
    now = time.monotonic()
    recent = [stamp for stamp in _calls.get(key_id, []) if now - stamp < 60]
    if len(recent) >= get_settings().webhook_rate_limit:
        _calls[key_id] = recent
        return True
    recent.append(now)
    _calls[key_id] = recent
    return False


def _reject_foreign_organization(parsed: BaseModel, organization_id: uuid.UUID) -> None:
    supplied = getattr(parsed, "organization_id", None)
    if supplied is not None and supplied != organization_id:
        raise AppError(403, "forbidden", "Webhook organization does not match the integration")


def _lead_processed(db: Session, organization_id: uuid.UUID, body: LeadCallback) -> dict[str, Any]:
    return complete_lead_callback(db, organization_id, body.workflow_run_id, body.lead_id)


def _follow_ups(db: Session, organization_id: uuid.UUID, _body: FollowUpQuery) -> dict[str, Any]:
    leads = db.scalars(
        select(Lead)
        .where(
            Lead.organization_id == organization_id,
            Lead.status.in_([LeadStatus.new, LeadStatus.contacted]),
        )
        .order_by(Lead.created_at.asc())
        .limit(50)
    )
    return {
        "leads": [
            {"id": str(lead.id), "title": lead.title, "status": lead.status.value} for lead in leads
        ]
    }


def _request_follow_up(
    db: Session, organization_id: uuid.UUID, body: FollowUpRequest
) -> dict[str, Any]:
    lead = crm.get_lead(db, organization_id, body.lead_id)
    actor = _admin_id(db, organization_id)
    recipient = "inbox@localhost"
    if lead.contact_id is not None:
        contact = crm.get_contact(db, organization_id, lead.contact_id)
        if contact.email:
            recipient = contact.email
    inquiry = Inquiry(
        organization_id=organization_id,
        subject=f"Follow-up: {lead.title}"[:200],
        body=body.body,
        lead_id=lead.id,
    )
    db.add(inquiry)
    db.flush()
    run = AgentRun(
        organization_id=organization_id,
        inquiry_id=inquiry.id,
        started_by=actor,
        status=RunStatus.awaiting_approval,
    )
    db.add(run)
    db.flush()
    approval = create_approval(
        db,
        organization_id=organization_id,
        run_id=run.id,
        requested_by=actor,
        action_type=ActionType.prepare_customer_response,
        payload={
            "lead_id": str(lead.id),
            "body": body.body,
            "to": recipient,
            "subject": f"Follow-up: {lead.title}"[:200],
        },
        position=0,
        commit=False,
    )
    db.add(
        AgentEvent(
            organization_id=organization_id,
            run_id=run.id,
            step="follow_up",
            status="awaiting_approval",
            detail={"lead_id": str(lead.id), "approval_id": str(approval.id)},
        )
    )
    return {
        "approval_id": str(approval.id),
        "run_id": str(run.id),
        "status": approval.status.value,
    }


def _admin_id(db: Session, organization_id: uuid.UUID) -> uuid.UUID:
    user_id = db.scalar(
        select(Membership.user_id)
        .where(
            Membership.organization_id == organization_id,
            Membership.role == MembershipRole.admin,
        )
        .order_by(Membership.created_at.asc())
        .limit(1)
    )
    if user_id is None:
        raise AppError(
            409, "approval_unavailable", "This organization has no admin to own the follow-up"
        )
    return user_id
