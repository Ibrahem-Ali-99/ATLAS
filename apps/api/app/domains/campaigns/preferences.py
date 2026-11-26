"""Recipient-scoped campaign preference links and durable suppressions."""

import hashlib
import hmac
import re
import uuid
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.audit.service import record_event
from app.domains.campaigns.models import Campaign, CampaignDelivery, CampaignSuppression

_TOKEN = re.compile(r"([0-9a-f]{32})\.([0-9a-f]{64})")


def token_for(delivery_id: uuid.UUID) -> str:
    settings = get_settings()
    key = settings.campaign_link_secret or settings.secret_key
    signature = hmac.new(
        key.encode(), b"campaign-unsubscribe:" + delivery_id.bytes, hashlib.sha256
    ).hexdigest()
    return f"{delivery_id.hex}.{signature}"


def public_origin() -> str:
    settings = get_settings()
    value = settings.campaign_public_url or (
        "http://127.0.0.1:8000" if settings.email_mode == "sandbox" else ""
    )
    try:
        parsed = urlsplit(value.rstrip("/"))
        if (
            parsed.hostname
            and not parsed.username
            and not parsed.password
            and not (parsed.path or parsed.query or parsed.fragment)
            and (
                parsed.scheme == "https"
                or (
                    settings.email_mode == "sandbox"
                    and parsed.scheme == "http"
                    and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                )
            )
        ):
            return value.rstrip("/")
    except ValueError:
        pass
    raise AppError(503, "campaign_public_url_required", "Configure the campaign HTTPS origin")


def delivery_for_token(db: Session, token: str) -> tuple[uuid.UUID, CampaignDelivery]:
    match = _TOKEN.fullmatch(token)
    if match is not None:
        delivery_id = uuid.UUID(hex=match.group(1))
        if hmac.compare_digest(token, token_for(delivery_id)):
            row = db.execute(
                select(Campaign.organization_id, CampaignDelivery)
                .join(Campaign, Campaign.id == CampaignDelivery.campaign_id)
                .where(CampaignDelivery.id == delivery_id, CampaignDelivery.claimed_at.is_not(None))
            ).one_or_none()
            if row is not None:
                return row[0], row[1]
    raise AppError(404, "unsubscribe_link_invalid", "This unsubscribe link is unavailable")


def suppress_address(
    db: Session,
    organization_id: uuid.UUID,
    email: str,
    reason: str,
    *,
    actor_id: uuid.UUID | None = None,
) -> None:
    inserted = db.scalar(
        insert(CampaignSuppression)
        .values(organization_id=organization_id, email=email.strip().lower(), reason=reason)
        .on_conflict_do_nothing(
            index_elements=[CampaignSuppression.organization_id, CampaignSuppression.email]
        )
        .returning(CampaignSuppression.id)
    )
    if inserted is not None:
        record_event(
            db,
            organization_id,
            "campaign.recipient_suppressed",
            {"suppression_id": str(inserted), "reason": reason},
            actor_id=actor_id,
        )
