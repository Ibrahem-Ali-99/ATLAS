# ruff: noqa: E501
"""Copy sealed provider grants into the Harbor showcase.

The source workspace keeps its customers. Harbor receives integration
settings and encrypted credentials only, with another workspace's delivery
evidence removed. A copied grant is not verified until that provider accepts
a new request in Harbor.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.automation.models import WebhookKey
from app.domains.automation.signatures import open_integration_secret, seal_integration_secret
from app.domains.crm.models import Company
from app.domains.identity.models import Organization
from app.domains.integrations.calendar_models import GoogleCalendarConnection
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType
from app.domains.integrations.resend_credentials import TEST_EVIDENCE_KEYS, TEST_RECIPIENT_KEY
from app.domains.integrations.whatsapp_test import PUBLIC_CONFIG_KEYS

HARBOR_SLUG = "harbor-showcase"
SOURCE_SLUG = "atlas-demo"

_CONFIG_KEYS: dict[IntegrationType, frozenset[str]] = {
    IntegrationType.chat: frozenset({"base_url", "model"}),
    IntegrationType.embedding: frozenset({"base_url", "model", "dimensions"}),
    IntegrationType.email: frozenset({"host", "port", "from_address", "use_tls", "starttls"}),
    IntegrationType.whatsapp: PUBLIC_CONFIG_KEYS,
    IntegrationType.n8n: frozenset(),
}


@dataclass(frozen=True)
class GrantResult:
    kind: str
    status: str
    code: str | None = None


def showcase_organization(db: Session) -> Organization:
    organization = db.scalar(select(Organization).where(Organization.slug == HARBOR_SLUG))
    if organization is None:
        raise AppError(
            404, "harbor_missing", "The Harbor showcase organization is not in this database"
        )
    return organization


def source_organization(db: Session) -> Organization:
    organization = db.scalar(select(Organization).where(Organization.slug == SOURCE_SLUG))
    if organization is None:
        raise AppError(
            404,
            "provider_source_missing",
            "The operational workspace that holds the verified grants is not in this database",
        )
    return organization


def restore_grants(source: Session, harbor: Session) -> list[GrantResult]:
    """Copy grants. Does not read or write companies, contacts, or messages."""

    origin = source_organization(source)
    destination = showcase_organization(harbor)
    before = _company_count(harbor, destination.id)
    results = [
        _copy_integration(source, harbor, origin.id, destination.id, kind)
        for kind in IntegrationType
    ]
    results.append(_copy_calendar(source, harbor, origin.id, destination.id))
    results.append(_copy_webhook_key(source, harbor, origin.id, destination.id))
    harbor.commit()
    if _company_count(harbor, destination.id) != before:
        raise AppError(
            500, "harbor_customer_copy", "Harbor provider restore changed company records"
        )
    return results


def _company_count(db: Session, organization_id: uuid.UUID) -> int:
    return len(
        list(db.scalars(select(Company.id).where(Company.organization_id == organization_id)))
    )


def _copy_integration(
    source: Session,
    harbor: Session,
    source_id: uuid.UUID,
    harbor_id: uuid.UUID,
    kind: IntegrationType,
) -> GrantResult:
    existing = harbor.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == harbor_id,
            IntegrationConfig.integration_type == kind,
        )
    )
    if existing is not None:
        return GrantResult(kind.value, "already_present")
    record = source.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == source_id,
            IntegrationConfig.integration_type == kind,
            IntegrationConfig.status == IntegrationStatus.configured,
        )
    )
    if record is None:
        return GrantResult(kind.value, "absent")
    try:
        sealed = _scrubbed_secret(record)
        config = _public_config(kind, record.config)
    except AppError as exc:
        return GrantResult(kind.value, "blocked", exc.code)
    harbor.add(
        IntegrationConfig(
            organization_id=harbor_id,
            integration_type=kind,
            provider=record.provider,
            config=config,
            encrypted_credentials=sealed,
            status=IntegrationStatus.configured,
            credential_version=1,
            verified_at=None,
            verification_detail=None,
        )
    )
    harbor.flush()
    return GrantResult(kind.value, "copied")


def _public_config(kind: IntegrationType, config: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    allowed = _CONFIG_KEYS[kind]
    return {key: value for key, value in config.items() if key in allowed}


def _scrubbed_secret(record: IntegrationConfig) -> str | None:
    if not record.encrypted_credentials:
        return None
    opened = open_integration_secret(record.encrypted_credentials)
    if record.integration_type != IntegrationType.email:
        return seal_integration_secret(opened)
    try:
        parsed = json.loads(opened)
    except json.JSONDecodeError as exc:
        raise AppError(422, "email_credentials_invalid", "Email credentials are invalid") from exc
    if not isinstance(parsed, dict):
        raise AppError(422, "email_credentials_invalid", "Email credentials are invalid")
    cleaned = {key: value for key, value in parsed.items() if key not in TEST_EVIDENCE_KEYS}
    cleaned.pop(TEST_RECIPIENT_KEY, None)
    return seal_integration_secret(json.dumps(cleaned))


def _copy_calendar(
    source: Session,
    harbor: Session,
    source_id: uuid.UUID,
    harbor_id: uuid.UUID,
) -> GrantResult:
    existing = harbor.get(GoogleCalendarConnection, harbor_id)
    if existing is not None and existing.encrypted_token:
        return GrantResult("google_calendar", "already_present")
    record = source.get(GoogleCalendarConnection, source_id)
    if record is None or not record.encrypted_token:
        return GrantResult("google_calendar", "absent")
    conflict = harbor.scalar(
        select(GoogleCalendarConnection.organization_id).where(
            GoogleCalendarConnection.calendar_id == record.calendar_id,
            GoogleCalendarConnection.encrypted_token.is_not(None),
            GoogleCalendarConnection.organization_id != harbor_id,
        )
    )
    if conflict is not None:
        return GrantResult("google_calendar", "blocked", "calendar_already_connected")
    try:
        sealed = seal_integration_secret(open_integration_secret(record.encrypted_token))
    except AppError as exc:
        return GrantResult("google_calendar", "blocked", exc.code)
    if existing is None:
        harbor.add(
            GoogleCalendarConnection(
                organization_id=harbor_id,
                calendar_id=record.calendar_id,
                calendar_name=record.calendar_name,
                encrypted_token=sealed,
                connected_at=record.connected_at,
                connection_error=None,
            )
        )
    else:
        existing.calendar_id = record.calendar_id
        existing.calendar_name = record.calendar_name
        existing.encrypted_token = sealed
        existing.connected_at = record.connected_at
        existing.connection_error = None
    harbor.flush()
    return GrantResult("google_calendar", "copied")


def _copy_webhook_key(
    source: Session,
    harbor: Session,
    source_id: uuid.UUID,
    harbor_id: uuid.UUID,
) -> GrantResult:
    existing = harbor.scalar(select(WebhookKey).where(WebhookKey.organization_id == harbor_id))
    if existing is not None and existing.revoked_at is None:
        return GrantResult("n8n_signing_key", "already_present")
    record = source.scalar(
        select(WebhookKey).where(
            WebhookKey.organization_id == source_id,
            WebhookKey.revoked_at.is_(None),
        )
    )
    if record is None:
        return GrantResult("n8n_signing_key", "absent")
    try:
        sealed = seal_integration_secret(open_integration_secret(record.secret))
    except AppError as exc:
        return GrantResult("n8n_signing_key", "blocked", exc.code)
    if existing is None:
        harbor.add(WebhookKey(organization_id=harbor_id, name=record.name, secret=sealed))
    else:
        existing.name = record.name
        existing.secret = sealed
        existing.revoked_at = None
        existing.rotated_at = datetime.now(UTC)
    harbor.flush()
    return GrantResult("n8n_signing_key", "copied")
