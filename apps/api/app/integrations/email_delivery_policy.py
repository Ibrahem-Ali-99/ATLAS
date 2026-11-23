"""Fail-closed gates for future organization-specific live email delivery.

This module only evaluates eligibility.  Actual delivery remains sandbox-only in
``app.integrations.email`` until a later, explicitly enabled phase.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from email.utils import parseaddr

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.automation.models import ExecutionIntent
from app.domains.crm.models import Contact
from app.domains.integrations.domain_models import DomainVerificationStatus, EmailDomainVerification
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType


@dataclass(frozen=True)
class LiveDeliveryEligibility:
    eligible: bool
    reason: str | None = None


def live_delivery_eligibility(
    db: Session,
    intent: ExecutionIntent,
    *,
    current_recipient: str | None = None,
) -> LiveDeliveryEligibility:
    """Evaluate all live-delivery gates for an immutable approved intent.

    The caller must still keep sandbox transport active.  This function never
    opens credentials and never sends a message.
    """
    config = db.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == intent.organization_id,
            IntegrationConfig.integration_type == IntegrationType.email,
        )
    )
    if config is None:
        return LiveDeliveryEligibility(False, "email_integration_missing")
    if config.status != IntegrationStatus.configured:
        return LiveDeliveryEligibility(False, "email_integration_disabled")
    if not config.encrypted_credentials:
        return LiveDeliveryEligibility(False, "email_credentials_missing")
    settings = config.config if isinstance(config.config, dict) else {}
    if settings.get("live_delivery_enabled") is not True:
        return LiveDeliveryEligibility(False, "live_delivery_not_enabled")
    if config.verified_at is None:
        return LiveDeliveryEligibility(False, "smtp_not_verified")
    sender = settings.get("from_address")
    sender_domain = _domain(sender) if isinstance(sender, str) else None
    if sender_domain is None:
        return LiveDeliveryEligibility(False, "sender_address_invalid")
    verified_domain = db.scalar(
        select(EmailDomainVerification).where(
            EmailDomainVerification.organization_id == intent.organization_id,
            EmailDomainVerification.domain == sender_domain,
            EmailDomainVerification.provider == "resend",
            EmailDomainVerification.status == DomainVerificationStatus.verified,
        )
    )
    if verified_domain is None or verified_domain.verified_at is None:
        return LiveDeliveryEligibility(False, "sender_domain_not_verified")

    payload = intent.payload if isinstance(intent.payload, dict) else {}
    recipient = payload.get("to")
    snapshot = payload.get("recipient_snapshot")
    contact_id = payload.get("contact_id")
    if not isinstance(recipient, str) or not isinstance(snapshot, str) or not contact_id:
        return LiveDeliveryEligibility(False, "recipient_snapshot_missing")
    if current_recipient is not None and _normalize(current_recipient) != _normalize(snapshot):
        return LiveDeliveryEligibility(False, "recipient_changed")
    try:
        contact_uuid = uuid.UUID(str(contact_id))
    except ValueError:
        return LiveDeliveryEligibility(False, "recipient_invalid")
    contact = db.scalar(
        select(Contact).where(
            Contact.id == contact_uuid,
            Contact.organization_id == intent.organization_id,
        )
    )
    if contact is None or not contact.email:
        return LiveDeliveryEligibility(False, "recipient_not_owned")
    if _normalize(contact.email) != _normalize(snapshot) or _normalize(recipient) != _normalize(
        snapshot
    ):
        return LiveDeliveryEligibility(False, "recipient_changed")
    allowed_domains = settings.get("allowed_recipient_domains", [])
    if not isinstance(allowed_domains, list) or not all(
        isinstance(value, str) for value in allowed_domains
    ):
        return LiveDeliveryEligibility(False, "recipient_policy_invalid")
    domain = _normalize(recipient).rsplit("@", 1)[1]
    if allowed_domains and domain not in {
        value.casefold().lstrip("@") for value in allowed_domains
    }:
        return LiveDeliveryEligibility(False, "recipient_domain_disallowed")
    return LiveDeliveryEligibility(True)


def _normalize(value: str) -> str:
    _, address = parseaddr(value.strip())
    return address.casefold()


def _domain(value: str) -> str | None:
    address = _normalize(value)
    if "@" not in address:
        return None
    return address.rsplit("@", 1)[1]
