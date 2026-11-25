import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select

from app.core.errors import AppError
from app.domains.campaigns.models import (
    Campaign,
    CampaignSuppression,
    CustomerSegment,
    MarketingConsent,
)
from app.domains.crm.models import Contact, Lead
from app.domains.identity.dependencies import CsrfMember, DbSession, Member

router = APIRouter(prefix="/organizations/{organization_id}", tags=["campaigns"])
ALLOWED = {"lead_status", "owner_user_id", "contact_email"}


class SegmentBody(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    logic: str = Field(default="and", pattern="^(and|or)$")
    conditions: list[dict[str, str]] = Field(min_length=1, max_length=10)


class CampaignBody(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    segment_id: uuid.UUID | None = None
    subject: str | None = None
    body: str | None = None
    objective: str | None = None


def _conditions(body: SegmentBody, organization_id: uuid.UUID) -> list[Any]:
    clauses = []
    for item in body.conditions:
        field, operator, value = item.get("field"), item.get("operator"), item.get("value")
        if field not in ALLOWED or operator != "eq" or not value:
            raise AppError(422, "invalid_segment_condition", "Unsupported segment condition")
        if field == "lead_status":
            clauses.append(Lead.status == value)
        elif field == "owner_user_id":
            clauses.append(Lead.owner_user_id == value)
        else:
            clauses.append(Contact.email == value.lower())
    return clauses


def _preview(
    db: DbSession, organization_id: uuid.UUID, definition: dict[str, Any]
) -> dict[str, int]:
    conditions = []
    for item in definition["conditions"]:
        field, value = item["field"], item["value"]
        conditions.append(
            Lead.status == value
            if field == "lead_status"
            else Lead.owner_user_id == value
            if field == "owner_user_id"
            else Contact.email == value.lower()
        )
    query = (
        select(func.count(func.distinct(Contact.id)), func.count(func.distinct(Lead.id)))
        .select_from(Contact)
        .outerjoin(Lead, Lead.contact_id == Contact.id)
        .where(Contact.organization_id == organization_id)
    )
    if conditions:
        query = query.where(or_(*conditions) if definition["logic"] == "or" else and_(*conditions))
    contacts, leads = db.execute(query).one()
    return {"contacts": int(contacts or 0), "leads": int(leads or 0)}


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
    _conditions(body, member.organization.id)
    definition = {"logic": body.logic, "conditions": body.conditions}
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
    return [
        {
            "id": row.id,
            "name": row.name,
            "status": row.status,
            "channel": row.channel,
            "segment_id": row.segment_id,
            "subject": row.subject,
        }
        for row in rows
    ]


@router.patch("/segments/{segment_id}")
def update_segment(
    segment_id: uuid.UUID, body: SegmentBody, member: CsrfMember, db: DbSession
) -> dict[str, Any]:
    _conditions(body, member.organization.id)
    row = db.scalar(
        select(CustomerSegment).where(
            CustomerSegment.id == segment_id,
            CustomerSegment.organization_id == member.organization.id,
        )
    )
    if row is None:
        raise AppError(404, "segment_not_found", "Segment not found")
    row.name = body.name
    row.definition = {"logic": body.logic, "conditions": body.conditions}
    db.commit()
    return {
        "id": row.id,
        "name": row.name,
        "definition": row.definition,
        "preview": _preview(db, member.organization.id, row.definition),
    }


@router.post("/segments/preview")
def preview_segment(body: SegmentBody, member: Member, db: DbSession) -> dict[str, int]:
    _conditions(body, member.organization.id)
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
    return {"id": row.id, "name": row.name, "status": row.status, "channel": row.channel}


@router.post("/campaigns/{campaign_id}/recipients/preview")
def recipient_preview(campaign_id: uuid.UUID, member: Member, db: DbSession) -> dict[str, int]:
    campaign = db.scalar(
        select(Campaign).where(
            Campaign.id == campaign_id, Campaign.organization_id == member.organization.id
        )
    )
    if campaign is None:
        raise AppError(404, "campaign_not_found", "Campaign not found")
    contacts = list(
        db.scalars(
            select(Contact)
            .where(Contact.organization_id == member.organization.id, Contact.email.is_not(None))
            .limit(1000)
        )
    )
    emails = [item.email.lower() for item in contacts if item.email]
    suppressed = set(
        db.scalars(
            select(CampaignSuppression.email).where(
                CampaignSuppression.organization_id == member.organization.id,
                CampaignSuppression.email.in_(emails),
            )
        )
    )
    consented = set(
        db.scalars(
            select(MarketingConsent.contact_id).where(
                MarketingConsent.organization_id == member.organization.id,
                MarketingConsent.status == "granted",
                MarketingConsent.contact_id.in_([item.id for item in contacts]),
            )
        )
    )
    valid = len(emails)
    suppressed_count = sum(email in suppressed for email in emails)
    consented_count = sum(item.id in consented for item in contacts)
    eligible = sum(
        1
        for item in contacts
        if item.email is not None and item.email.lower() not in suppressed and item.id in consented
    )
    return {
        "matching_contacts": len(contacts),
        "valid_email": valid,
        "suppressed": suppressed_count,
        "consented": consented_count,
        "missing_consent": valid - consented_count,
        "eligible": eligible,
    }


@router.post("/contacts/{contact_id}/marketing-consent", status_code=201)
def grant_consent(
    contact_id: uuid.UUID, source: str, member: CsrfMember, db: DbSession
) -> dict[str, Any]:
    if (
        db.scalar(
            select(Contact.id).where(
                Contact.id == contact_id, Contact.organization_id == member.organization.id
            )
        )
        is None
    ):
        raise AppError(404, "contact_not_found", "Contact not found")
    row = MarketingConsent(
        organization_id=member.organization.id,
        contact_id=contact_id,
        status="granted",
        source=source,
        consented_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    return {"contact_id": row.contact_id, "status": row.status, "source": row.source}


@router.patch("/campaigns/{campaign_id}")
def update_campaign(
    campaign_id: uuid.UUID, body: CampaignBody, member: CsrfMember, db: DbSession
) -> dict[str, Any]:
    row = db.scalar(
        select(Campaign).where(
            Campaign.id == campaign_id, Campaign.organization_id == member.organization.id
        )
    )
    if row is None:
        raise AppError(404, "campaign_not_found", "Campaign not found")
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
    db.commit()
    return {
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "channel": row.channel,
        "segment_id": row.segment_id,
        "subject": row.subject,
    }


@router.post("/campaign-suppressions", status_code=201)
def suppress(email: str, member: CsrfMember, db: DbSession) -> dict[str, Any]:
    row = CampaignSuppression(organization_id=member.organization.id, email=email.lower())
    db.add(row)
    db.commit()
    return {"email": row.email, "suppressed": True}
