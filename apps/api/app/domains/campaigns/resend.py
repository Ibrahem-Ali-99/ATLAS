"""Send campaign mail through Resend and reconcile authenticated delivery events."""

import base64
import binascii
import hashlib
import hmac
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

import httpx
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.campaigns.models import Campaign, CampaignDelivery
from app.domains.campaigns.preferences import public_origin, suppress_address
from app.domains.integrations.domain_models import DomainVerificationStatus, EmailDomainVerification
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType
from app.domains.integrations.service import open_credentials
from app.integrations.email import DeliveryReceipt, OutboundEmail, normalize_recipient
from app.integrations.outcomes import DeliveryFailed, OutcomeUncertain

_ADDRESS = TypeAdapter(EmailStr)
_FEEDBACK = {
    "email.delivered": "delivered",
    "email.failed": "failed",
    "email.bounced": "bounced",
    "email.complained": "complained",
}
_PRECEDENCE = {"accepted": 0, "delivered": 1, "failed": 2, "bounced": 3, "complained": 4}


def _webhook_key() -> bytes:
    value = get_settings().resend_campaign_webhook_secret
    try:
        if value.startswith("whsec_"):
            key = base64.b64decode(value[6:], validate=True)
            if len(key) >= 16:
                return key
    except (ValueError, binascii.Error):
        pass
    raise AppError(503, "campaign_webhook_unconfigured", "Configure campaign delivery feedback")


def live_sender(db: Session, organization_id: uuid.UUID) -> tuple[str, str]:
    settings = get_settings()
    if not (
        settings.email_mode == "live"
        and settings.email_live_enabled
        and settings.campaign_live_enabled
    ):
        raise AppError(409, "campaign_live_disabled", "Live campaign delivery is disabled")
    public_origin()
    _webhook_key()
    if len(settings.campaign_link_secret) < 32:
        raise AppError(503, "campaign_link_unconfigured", "Configure campaign preference signing")
    config = db.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == organization_id,
            IntegrationConfig.integration_type == IntegrationType.email,
            IntegrationConfig.status == IntegrationStatus.configured,
        )
    )
    if config is None or config.provider != "smtp":
        raise AppError(
            409, "campaign_email_unconfigured", "Configure the workspace Email integration"
        )
    try:
        address = _ADDRESS.validate_python(config.config.get("from_address"))
    except ValidationError:
        raise AppError(409, "campaign_sender_invalid", "Enter a valid campaign sender") from None
    domain = db.scalar(
        select(EmailDomainVerification.id).where(
            EmailDomainVerification.organization_id == organization_id,
            EmailDomainVerification.domain == address.rsplit("@", 1)[1].lower(),
            EmailDomainVerification.provider == "resend",
            EmailDomainVerification.status == DomainVerificationStatus.verified,
            EmailDomainVerification.credential_version == config.credential_version,
        )
    )
    if domain is None:
        raise AppError(409, "campaign_domain_unverified", "Verify the campaign sender domain")
    try:
        credentials = json.loads(open_credentials(config) or "{}")
    except (TypeError, ValueError):
        credentials = {}
    key = credentials.get("resend_api_key") if isinstance(credentials, dict) else None
    if not isinstance(key, str) or not key.strip():
        raise AppError(409, "campaign_resend_unconfigured", "Configure the Resend sending key")
    return address, key


def send_resend(message: OutboundEmail, *, sender: str, api_key: str) -> DeliveryReceipt:
    try:
        result = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Idempotency-Key": message.idempotency_key,
            },
            json={
                "from": sender,
                "to": [normalize_recipient(message.recipient)],
                "subject": message.subject,
                "text": message.body,
                "headers": {
                    "List-Unsubscribe": f"<{message.unsubscribe_url}>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                },
            },
            timeout=10,
        )
    except httpx.RequestError as exc:
        raise OutcomeUncertain("resend_transport_error") from exc
    if result.status_code >= 500 or result.status_code == 408:
        raise OutcomeUncertain("resend_unavailable")
    if not result.is_success:
        raise DeliveryFailed("resend_rejected")
    try:
        message_id = str(uuid.UUID(result.json()["id"]))
    except (AttributeError, ValueError, KeyError, TypeError):
        raise OutcomeUncertain("resend_receipt_invalid") from None
    return DeliveryReceipt(message_id, "live")


def _verified_event(headers: Mapping[str, str], raw: bytes) -> dict[str, object]:
    key = _webhook_key()
    event_id = headers.get("svix-id", "")
    stamp = headers.get("svix-timestamp", "")
    signatures = headers.get("svix-signature", "")
    if (
        not event_id
        or len(event_id) > 128
        or len(stamp) > 12
        or not stamp.isascii()
        or not stamp.isdecimal()
        or abs(datetime.now(UTC).timestamp() - int(stamp)) > 300
        or len(signatures) > 1024
    ):
        raise AppError(401, "campaign_webhook_signature", "Invalid campaign feedback signature")
    digest = hmac.new(key, f"{event_id}.{stamp}.".encode() + raw, hashlib.sha256).digest()
    signature = "v1," + base64.b64encode(digest).decode()
    if not any(
        hmac.compare_digest(signature.encode(), item.encode()) for item in signatures.split()
    ):
        raise AppError(401, "campaign_webhook_signature", "Invalid campaign feedback signature")
    try:
        event = json.loads(raw)
        if isinstance(event, dict):
            return event
    except (ValueError, RecursionError):
        pass
    raise AppError(422, "campaign_webhook_payload", "Invalid campaign feedback payload")


def accept_feedback(db: Session, headers: Mapping[str, str], raw: bytes) -> None:
    event = _verified_event(headers, raw)
    event_type = event.get("type")
    if not isinstance(event_type, str) or event_type not in _FEEDBACK:
        return
    data = event.get("data")
    try:
        message_id = str(uuid.UUID(str(data["email_id"]))) if isinstance(data, dict) else None
    except (KeyError, ValueError):
        message_id = None
    if message_id is None:
        raise AppError(422, "campaign_webhook_payload", "Campaign feedback requires a message ID")

    # Lock the campaign before the delivery to match dispatch and cancellation.
    match = db.execute(
        select(Campaign, CampaignDelivery.id)
        .join(CampaignDelivery)
        .where(Campaign.delivery_mode == "live", CampaignDelivery.message_id == message_id)
        .with_for_update(of=Campaign)
    ).one_or_none()
    if match is None:
        raise AppError(503, "campaign_receipt_pending", "Campaign receipt has not been recorded")
    campaign, delivery_id = match
    delivery = db.get_one(CampaignDelivery, delivery_id, with_for_update=True)
    status = _FEEDBACK[event_type]
    prior = _PRECEDENCE.get(delivery.status)
    if prior is not None and _PRECEDENCE[status] > prior:
        delivery.status = status
        if status in {"bounced", "complained"}:
            suppress_address(db, campaign.organization_id, delivery.email, status)
        if status != "delivered" and campaign.status == "completed":
            campaign.status = "completed_with_errors"
        campaign.updated_at = datetime.now(UTC)
    db.commit()
