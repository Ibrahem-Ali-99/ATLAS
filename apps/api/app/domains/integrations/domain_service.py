from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.automation.signatures import open_integration_secret
from app.domains.integrations.domain_models import (
    DomainVerificationStatus,
    EmailDomainVerification,
)
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType
from app.integrations.domain_verification import DomainProvider, ResendDomainProvider


def provider_for_email(db: Session, organization_id: uuid.UUID) -> DomainProvider:
    config = db.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == organization_id,
            IntegrationConfig.integration_type == IntegrationType.email,
        )
    )
    if (
        config is None
        or config.provider != "smtp"
        or not config.encrypted_credentials
        or config.status == IntegrationStatus.disabled
    ):
        raise AppError(
            503, "email_provider_unconfigured", "Email provider credentials are unavailable."
        )
    try:
        raw = json.loads(open_integration_secret(config.encrypted_credentials))
    except (json.JSONDecodeError, TypeError) as exc:
        raise AppError(
            503, "email_provider_unconfigured", "Email provider credentials are invalid."
        ) from exc
    token = raw.get("resend_api_key") if isinstance(raw, dict) else None
    if not isinstance(token, str) or not token.strip():
        raise AppError(
            503,
            "email_provider_unconfigured",
            "A Resend domain-verification token is required.",
        )
    return ResendDomainProvider(token)


def register_domain(
    db: Session, organization_id: uuid.UUID, domain: str
) -> EmailDomainVerification:
    normalized = domain.strip().casefold().rstrip(".")
    if not normalized or "@" in normalized or "." not in normalized:
        raise AppError(422, "invalid_domain", "A valid sending domain is required.")
    email_config = db.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == organization_id,
            IntegrationConfig.integration_type == IntegrationType.email,
        )
    )
    if email_config is None:
        raise AppError(503, "email_provider_unconfigured", "Email provider is unavailable.")
    record = db.scalar(
        select(EmailDomainVerification).where(
            EmailDomainVerification.organization_id == organization_id,
            EmailDomainVerification.domain == normalized,
        )
    )
    if record is not None and record.status not in {
        DomainVerificationStatus.failed,
        DomainVerificationStatus.revoked,
    }:
        raise AppError(409, "domain_already_registered", "This domain is already registered.")
    result = provider_for_email(db, organization_id).register(normalized)
    if record is None:
        record = EmailDomainVerification(organization_id=organization_id, domain=normalized)
        db.add(record)
    record.provider = "resend"
    record.credential_version = email_config.credential_version
    record.status = (
        DomainVerificationStatus.verified if result.verified else DomainVerificationStatus.pending
    )
    record.dns_records = [item.__dict__ for item in result.records]
    record.provider_domain_id = result.provider_domain_id
    record.evidence = result.evidence
    record.verified_at = datetime.now(UTC) if result.verified else None
    record.checked_at = datetime.now(UTC)
    db.flush()
    return record


def check_domain(db: Session, record: EmailDomainVerification) -> EmailDomainVerification:
    email_config = db.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == record.organization_id,
            IntegrationConfig.integration_type == IntegrationType.email,
        )
    )
    provider_domain_id = record.provider_domain_id
    if (
        email_config is None
        or not provider_domain_id
        or record.status == DomainVerificationStatus.revoked
    ):
        raise AppError(
            409, "domain_unavailable", "Register this sending domain before verification"
        )
    provider = provider_for_email(db, record.organization_id)
    result = provider.status(provider_domain_id)
    if not result.verified:
        provider.start_verification(provider_domain_id)
        result = provider.status(provider_domain_id)
    record.status = (
        DomainVerificationStatus.verified if result.verified else DomainVerificationStatus.pending
    )
    record.dns_records = [item.__dict__ for item in result.records]
    record.evidence = result.evidence
    record.checked_at = datetime.now(UTC)
    record.verified_at = datetime.now(UTC) if result.verified else None
    record.credential_version = email_config.credential_version
    return record


def revoke_domain(db: Session, record: EmailDomainVerification) -> EmailDomainVerification:
    if record.provider_domain_id:
        provider_for_email(db, record.organization_id).revoke(record.provider_domain_id)
    record.status = DomainVerificationStatus.revoked
    record.verified_at = None
    record.checked_at = datetime.now(UTC)
    record.evidence = {"provider": record.provider, "status": "revoked"}
    return record
