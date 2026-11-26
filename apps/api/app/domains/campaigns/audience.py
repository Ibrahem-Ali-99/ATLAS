import uuid
from typing import Any

from sqlalchemy import and_, func, or_, select, true

from app.core.errors import AppError
from app.domains.campaigns.models import CampaignSuppression, MarketingConsent
from app.domains.crm.models import Contact, Lead, LeadStatus
from app.domains.provenance.origin import Origin

ALLOWED = {"lead_status", "owner_user_id", "contact_email"}


def segment_conditions(definition: dict[str, Any]) -> list[Any]:
    clauses = []
    for item in definition["conditions"]:
        field, operator, value = item.get("field"), item.get("operator"), item.get("value")
        if field not in ALLOWED or operator != "eq" or not value or not value.strip():
            raise AppError(422, "invalid_segment_condition", "Unsupported segment condition")
        value = value.strip()
        try:
            if field == "lead_status":
                clauses.append(Lead.status == LeadStatus(value))
            elif field == "owner_user_id":
                clauses.append(Lead.owner_user_id == uuid.UUID(value))
            else:
                clauses.append(func.lower(Contact.email) == value.lower())
        except ValueError as exc:
            raise AppError(
                422, "invalid_segment_condition", "The segment value is invalid"
            ) from exc
    return clauses


def segment_contact_query(
    query: Any,
    organization_id: uuid.UUID,
    definition: dict[str, Any],
    *,
    operational_only: bool = False,
) -> Any:
    conditions = segment_conditions(definition)
    query = (
        query.select_from(Contact)
        .outerjoin(
            Lead,
            and_(
                Lead.contact_id == Contact.id,
                Lead.organization_id == organization_id,
                Lead.archived_at.is_(None),
                Lead.origin == Origin.operational if operational_only else true(),
            ),
        )
        .where(Contact.organization_id == organization_id, Contact.archived_at.is_(None))
    )
    if operational_only:
        query = query.where(Contact.origin == Origin.operational)
    if conditions:
        query = query.where(or_(*conditions) if definition["logic"] == "or" else and_(*conditions))
    return query


def audience_filters(
    organization_id: uuid.UUID, definition: dict[str, Any], *, operational_only: bool = False
) -> tuple[Any, ...]:
    candidates = (
        segment_contact_query(
            select(Contact.id, func.lower(func.trim(Contact.email)).label("email")),
            organization_id,
            definition,
            operational_only=operational_only,
        )
        .distinct()
        .subquery()
    )
    latest_consent = (
        select(MarketingConsent.status)
        .where(
            MarketingConsent.organization_id == organization_id,
            MarketingConsent.contact_id == candidates.c.id,
        )
        .order_by(MarketingConsent.consented_at.desc(), MarketingConsent.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    suppressed = (
        select(CampaignSuppression.id)
        .where(
            CampaignSuppression.organization_id == organization_id,
            func.lower(func.trim(CampaignSuppression.email)) == candidates.c.email,
        )
        .exists()
    )
    valid = candidates.c.email.op("~")(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    consented = func.coalesce(latest_consent == "granted", False)
    return candidates, valid, consented, suppressed
