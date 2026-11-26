import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Form, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import AwareDatetime, BaseModel, EmailStr, Field
from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.audit.service import record_event
from app.domains.campaigns import dispatch
from app.domains.campaigns.audience import (
    audience_filters,
    segment_conditions,
    segment_contact_query,
)
from app.domains.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignSuppression,
    CustomerSegment,
    MarketingConsent,
)
from app.domains.campaigns.preferences import delivery_for_token, public_origin, suppress_address
from app.domains.campaigns.resend import accept_feedback, live_sender
from app.domains.crm.models import Contact, Lead
from app.domains.identity.dependencies import Admin, CsrfAdmin, CsrfMember, DbSession, Member

router = APIRouter(prefix="/organizations/{organization_id}", tags=["campaigns"])
preferences = APIRouter(prefix="/campaign-preferences", tags=["campaign preferences"])
feedback = APIRouter(prefix="/hooks/campaign-delivery", tags=["campaign delivery"])

_PREFERENCE_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; form-action 'self'; frame-ancestors 'none'",
}


@preferences.get("/{token}", response_class=HTMLResponse)
def unsubscribe_confirmation(token: str, db: DbSession) -> HTMLResponse:
    delivery_for_token(db, token)
    return HTMLResponse(
        '<!doctype html><html lang="en"><title>Unsubscribe</title>'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<main><h1>Unsubscribe from campaign emails</h1>"
        "<p>Confirm to stop receiving marketing email from this workspace.</p>"
        '<form method="post"><button type="submit" name="confirm" value="yes">'
        "Unsubscribe</button></form></main></html>",
        headers=_PREFERENCE_HEADERS,
    )


@preferences.post("/{token}", response_class=HTMLResponse)
def unsubscribe(
    token: str,
    db: DbSession,
    confirm: Annotated[str | None, Form(max_length=20)] = None,
    one_click: Annotated[str | None, Form(alias="List-Unsubscribe", max_length=20)] = None,
) -> HTMLResponse:
    organization_id, delivery = delivery_for_token(db, token)
    if confirm != "yes" and one_click != "One-Click":
        raise AppError(400, "unsubscribe_confirmation_required", "Confirm the unsubscribe request")
    suppress_address(db, organization_id, delivery.email, "unsubscribe")
    db.commit()
    return HTMLResponse(
        '<!doctype html><html lang="en"><title>Unsubscribed</title>'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<main><h1>Unsubscribed</h1>"
        "<p>You will no longer receive campaign emails from this workspace.</p></main></html>",
        headers=_PREFERENCE_HEADERS,
    )


@feedback.post("/resend", status_code=204)
async def resend_feedback(request: Request, db: DbSession) -> Response:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 128 * 1024:
            raise AppError(413, "campaign_webhook_too_large", "Campaign feedback is too large")
        body.extend(chunk)
    await run_in_threadpool(accept_feedback, db, request.headers, bytes(body))
    return Response(status_code=204)


class SegmentBody(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    logic: str = Field(default="and", pattern="^(and|or)$")
    conditions: list[dict[str, str]] = Field(min_length=1, max_length=10)


class CampaignBody(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    segment_id: uuid.UUID | None = None
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=20000)
    objective: str | None = None


def _preview(
    db: DbSession, organization_id: uuid.UUID, definition: dict[str, Any]
) -> dict[str, int]:
    query = select(func.count(func.distinct(Contact.id)), func.count(func.distinct(Lead.id)))
    contacts, leads = db.execute(segment_contact_query(query, organization_id, definition)).one()
    return {"contacts": int(contacts or 0), "leads": int(leads or 0)}


def _campaign(
    db: DbSession, organization_id: uuid.UUID, campaign_id: uuid.UUID, *, lock: bool = False
) -> Campaign:
    query = select(Campaign).where(
        Campaign.id == campaign_id, Campaign.organization_id == organization_id
    )
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise AppError(404, "campaign_not_found", "Campaign not found")
    return row


def _campaign_out(row: Campaign) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "channel": row.channel,
        "segment_id": row.segment_id,
        "subject": row.subject,
        "description": row.description,
        "objective": row.objective,
        "body": row.body,
        "updated_at": row.updated_at,
        "scheduled_at": row.scheduled_at,
        "finished_at": row.finished_at,
        "delivery_mode": row.delivery_mode,
    }


@router.get("/segments")
def list_segments(member: Member, db: DbSession) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(CustomerSegment)
        .where(CustomerSegment.organization_id == member.organization.id)
        .order_by(CustomerSegment.name)
        .limit(100)
    ).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "definition": row.definition,
            "preview": _preview(db, member.organization.id, row.definition),
        }
        for row in rows
    ]


@router.post("/segments", status_code=201)
def create_segment(body: SegmentBody, member: CsrfMember, db: DbSession) -> dict[str, Any]:
    definition = {"logic": body.logic, "conditions": body.conditions}
    segment_conditions(definition)
    row = CustomerSegment(
        organization_id=member.organization.id, name=body.name, definition=definition
    )
    db.add(row)
    db.commit()
    return {
        "id": row.id,
        "name": row.name,
        "definition": definition,
        "preview": _preview(db, member.organization.id, definition),
    }


@router.get("/campaigns")
def list_campaigns(member: Member, db: DbSession) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Campaign)
        .where(Campaign.organization_id == member.organization.id)
        .order_by(Campaign.created_at.desc())
        .limit(100)
    ).all()
    return [_campaign_out(row) for row in rows]


@router.get("/campaigns/{campaign_id}")
def campaign_detail(campaign_id: uuid.UUID, member: Member, db: DbSession) -> dict[str, Any]:
    row = _campaign(db, member.organization.id, campaign_id)
    return {**_campaign_out(row), "deliveries": dispatch.counts(db, row)}


class CampaignScheduleBody(BaseModel):
    scheduled_at: AwareDatetime | None = None
    delivery_mode: Literal["sandbox", "live"] = "sandbox"


@router.get("/campaign-transport")
def campaign_transport(admin: Admin, db: DbSession) -> dict[str, object]:
    mode = get_settings().email_mode
    try:
        public_origin()
        if mode == "live":
            live_sender(db, admin.organization.id)
    except AppError as exc:
        return {"mode": mode, "ready": False, "detail": exc.message}
    return {"mode": mode, "ready": True, "detail": None}


@router.post("/campaigns/{campaign_id}/schedule")
def schedule_campaign(
    campaign_id: uuid.UUID, body: CampaignScheduleBody, member: CsrfAdmin, db: DbSession
) -> dict[str, Any]:
    row = _campaign(db, member.organization.id, campaign_id, lock=True)
    recipient_count = dispatch.schedule(
        db, row, body.scheduled_at, delivery_mode=body.delivery_mode
    )
    record_event(
        db,
        member.organization.id,
        "campaign.scheduled",
        {
            "campaign_id": str(campaign_id),
            "scheduled_at": row.scheduled_at.isoformat() if row.scheduled_at else None,
            "recipient_count": recipient_count,
            "delivery_mode": row.delivery_mode,
        },
        actor_id=member.user.id,
    )
    db.commit()
    return {**_campaign_out(row), "deliveries": dispatch.counts(db, row)}


@router.post("/campaigns/{campaign_id}/cancel")
def cancel_campaign(campaign_id: uuid.UUID, member: CsrfAdmin, db: DbSession) -> dict[str, Any]:
    row = _campaign(db, member.organization.id, campaign_id, lock=True)
    dispatch.cancel(db, row)
    record_event(
        db,
        member.organization.id,
        "campaign.cancelled",
        {"campaign_id": str(campaign_id)},
        actor_id=member.user.id,
    )
    db.commit()
    return {**_campaign_out(row), "deliveries": dispatch.counts(db, row)}


@router.patch("/segments/{segment_id}")
def update_segment(
    segment_id: uuid.UUID, body: SegmentBody, member: CsrfMember, db: DbSession
) -> dict[str, Any]:
    definition = {"logic": body.logic, "conditions": body.conditions}
    segment_conditions(definition)
    row = db.scalar(
        select(CustomerSegment).where(
            CustomerSegment.id == segment_id,
            CustomerSegment.organization_id == member.organization.id,
        )
    )
    if row is None:
        raise AppError(404, "segment_not_found", "Segment not found")
    row.name = body.name
    row.definition = definition
    db.commit()
    return {
        "id": row.id,
        "name": row.name,
        "definition": row.definition,
        "preview": _preview(db, member.organization.id, row.definition),
    }


@router.post("/segments/preview")
def preview_segment(body: SegmentBody, member: Member, db: DbSession) -> dict[str, int]:
    return _preview(
        db, member.organization.id, {"logic": body.logic, "conditions": body.conditions}
    )


@router.post("/campaigns", status_code=201)
def create_campaign(body: CampaignBody, member: CsrfMember, db: DbSession) -> dict[str, Any]:
    if (
        body.segment_id is not None
        and db.scalar(
            select(CustomerSegment.id).where(
                CustomerSegment.id == body.segment_id,
                CustomerSegment.organization_id == member.organization.id,
            )
        )
        is None
    ):
        raise AppError(404, "segment_not_found", "Segment not found")
    row = Campaign(
        organization_id=member.organization.id,
        segment_id=body.segment_id,
        name=body.name,
        description=body.description,
        subject=body.subject,
        body=body.body,
        objective=body.objective,
    )
    db.add(row)
    db.commit()
    return _campaign_out(row)


@router.post("/campaigns/{campaign_id}/recipients/preview")
def recipient_preview(campaign_id: uuid.UUID, member: Member, db: DbSession) -> dict[str, int]:
    organization_id = member.organization.id
    campaign = _campaign(db, organization_id, campaign_id)
    segment = (
        db.scalar(
            select(CustomerSegment).where(
                CustomerSegment.id == campaign.segment_id,
                CustomerSegment.organization_id == organization_id,
            )
        )
        if campaign.segment_id
        else None
    )
    result = dict.fromkeys(
        (
            "matching_contacts",
            "valid_email",
            "suppressed",
            "consented",
            "missing_consent",
            "eligible",
        ),
        0,
    )
    if segment is None:
        return result

    mode = get_settings().email_mode if campaign.status == "draft" else campaign.delivery_mode
    candidates, valid, consented, suppressed = audience_filters(
        organization_id, segment.definition, operational_only=mode == "live"
    )
    counts = db.execute(
        select(
            func.count(),
            func.count().filter(valid),
            func.count().filter(valid, suppressed),
            func.count().filter(valid, consented),
            func.count().filter(valid, ~consented),
            func.count(func.distinct(candidates.c.email)).filter(valid, consented, ~suppressed),
        ).select_from(candidates)
    ).one()
    return dict(zip(result, (int(count) for count in counts), strict=True))


@router.get("/contacts/{contact_id}/marketing-consent")
def marketing_consent(contact_id: uuid.UUID, member: Member, db: DbSession) -> dict[str, Any]:
    row = db.execute(
        select(Contact.id, MarketingConsent.status, MarketingConsent.source)
        .outerjoin(
            MarketingConsent,
            and_(
                MarketingConsent.contact_id == Contact.id,
                MarketingConsent.organization_id == Contact.organization_id,
            ),
        )
        .where(Contact.id == contact_id, Contact.organization_id == member.organization.id)
    ).one_or_none()
    if row is None:
        raise AppError(404, "contact_not_found", "Contact not found")
    return {"contact_id": row.id, "status": row.status, "source": row.source}


class ConsentBody(BaseModel):
    source: str = Field(min_length=1, max_length=80)
    status: Literal["granted", "revoked"]


@router.post("/contacts/{contact_id}/marketing-consent", status_code=201)
def grant_consent(
    contact_id: uuid.UUID,
    member: CsrfMember,
    db: DbSession,
    body: ConsentBody | None = None,
    source: str | None = None,
    status: Literal["granted", "revoked"] = "granted",
) -> dict[str, Any]:
    contact = db.scalar(
        select(Contact)
        .where(Contact.id == contact_id, Contact.organization_id == member.organization.id)
        .with_for_update()
    )
    if contact is None:
        raise AppError(404, "contact_not_found", "Contact not found")
    clean_source = (body.source if body else source or "").strip()
    status = body.status if body else status
    if not 1 <= len(clean_source) <= 80:
        raise AppError(422, "invalid_consent_source", "Enter a consent source up to 80 characters")
    if status == "granted" and (not contact.email or contact.archived_at):
        raise AppError(409, "contact_not_eligible", "Use an active contact with an email address")
    now = datetime.now(UTC)
    db.execute(
        insert(MarketingConsent)
        .values(
            organization_id=member.organization.id,
            contact_id=contact_id,
            status=status,
            source=clean_source,
            consented_at=now,
        )
        .on_conflict_do_update(
            index_elements=[MarketingConsent.organization_id, MarketingConsent.contact_id],
            set_={"status": status, "source": clean_source, "consented_at": now},
        )
    )
    record_event(
        db,
        member.organization.id,
        "marketing_consent_changed",
        {
            "contact_id": str(contact_id),
            "status": status,
            "source": clean_source,
        },
        actor_id=member.user.id,
    )
    db.commit()
    return {"contact_id": contact_id, "status": status, "source": clean_source}


@router.patch("/campaigns/{campaign_id}")
def update_campaign(
    campaign_id: uuid.UUID, body: CampaignBody, member: CsrfMember, db: DbSession
) -> dict[str, Any]:
    row = _campaign(db, member.organization.id, campaign_id, lock=True)
    if row.status != "draft":
        raise AppError(409, "campaign_locked", "Only draft campaigns can be edited")
    if (
        body.segment_id is not None
        and db.scalar(
            select(CustomerSegment.id).where(
                CustomerSegment.id == body.segment_id,
                CustomerSegment.organization_id == member.organization.id,
            )
        )
        is None
    ):
        raise AppError(404, "segment_not_found", "Segment not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    row.updated_at = datetime.now(UTC)
    db.commit()
    return _campaign_out(row)


class SuppressionBody(BaseModel):
    email: EmailStr


@router.get("/campaign-suppressions")
def list_suppressions(
    admin: Admin, db: DbSession, offset: int = Query(0, ge=0)
) -> list[dict[str, object]]:
    rows = db.scalars(
        select(CampaignSuppression)
        .where(CampaignSuppression.organization_id == admin.organization.id)
        .order_by(CampaignSuppression.created_at.desc(), CampaignSuppression.id)
        .offset(offset)
        .limit(50)
    )
    return [
        {"email": row.email, "reason": row.reason, "created_at": row.created_at} for row in rows
    ]


@router.get("/campaigns/{campaign_id}/deliveries")
def list_deliveries(
    campaign_id: uuid.UUID,
    admin: Admin,
    db: DbSession,
    offset: int = Query(0, ge=0),
) -> list[dict[str, object]]:
    campaign = _campaign(db, admin.organization.id, campaign_id)
    rows = db.scalars(
        select(CampaignDelivery)
        .where(CampaignDelivery.campaign_id == campaign.id)
        .order_by(CampaignDelivery.email, CampaignDelivery.id)
        .offset(offset)
        .limit(50)
    )
    return [
        {"id": row.id, "email": row.email, "status": row.status, "claimed_at": row.claimed_at}
        for row in rows
    ]


@router.post("/campaign-suppressions", status_code=201)
def suppress(
    member: CsrfMember,
    db: DbSession,
    body: SuppressionBody | None = None,
    email: EmailStr | None = None,
) -> dict[str, Any]:
    address = body.email if body else email
    if not address:
        raise AppError(422, "email_required", "Enter the email address to suppress")
    normalized = address.lower()
    suppress_address(db, member.organization.id, normalized, "manual", actor_id=member.user.id)
    db.commit()
    return {"email": normalized, "suppressed": True}
