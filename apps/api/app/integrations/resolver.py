"""Tenant-scoped provider configuration resolution.

Resolution is deliberately request-scoped: encrypted credentials are opened only
while constructing a client and no client or secret is cached globally.
"""

import uuid
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.domains.automation.signatures import open_integration_secret
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType


def resolve_settings(
    db: Session,
    organization_id: uuid.UUID,
    kind: Literal["chat", "embedding"],
    *,
    base_settings: Settings | None = None,
    for_verification: bool = False,
) -> Settings:
    settings = base_settings or get_settings()
    record = (
        db.query(IntegrationConfig)
        .populate_existing()
        .filter(
            IntegrationConfig.organization_id == organization_id,
            IntegrationConfig.integration_type == IntegrationType(kind),
        )
        .one_or_none()
    )
    if record is None:
        return settings
    if record.status != IntegrationStatus.configured and not (
        for_verification and record.status == IntegrationStatus.verification_failed
    ):
        raise AppError(503, "integration_disabled", "The organization integration is disabled.")
    requires_credential = kind == "chat" or record.provider not in {"ollama", "double"}
    if requires_credential and not record.encrypted_credentials:
        raise AppError(
            503, "integration_unconfigured", "The organization integration has no credential."
        )
    credential = (
        open_integration_secret(record.encrypted_credentials)
        if record.encrypted_credentials
        else ""
    )
    if requires_credential and not credential.strip():
        raise AppError(
            503, "integration_unconfigured", "The organization integration has no credential."
        )
    config = record.config if isinstance(record.config, dict) else {}
    if kind == "chat":
        updates: dict[str, object] = {
            "llm_provider": record.provider,
            "llm_api_key": credential,
            "llm_base_url": _text(config, "base_url", settings.llm_base_url),
            "llm_model": _text(config, "model", settings.llm_model),
        }
    else:
        dimensions = _int(config, "dimensions", settings.embedding_dimensions)
        if dimensions not in {768, 1536}:
            raise AppError(
                503,
                "embedding_unconfigured",
                "The organization embedding dimensions are invalid.",
            )
        updates = {
            "embedding_provider": record.provider,
            "embedding_api_key": credential,
            "embedding_base_url": _text(config, "base_url", settings.embedding_base_url),
            "embedding_model": _text(config, "model", settings.embedding_model),
            "embedding_dimensions": dimensions,
        }
    try:
        return settings.model_copy(update=updates)
    except (TypeError, ValueError) as exc:
        raise AppError(
            503,
            "integration_unconfigured",
            "The organization integration configuration is invalid.",
        ) from exc


def _text(config: dict[str, object], key: str, default: str) -> str:
    value = config.get(key, default)
    return value.strip() if isinstance(value, str) and value.strip() else default


def _int(config: dict[str, object], key: str, default: int) -> int:
    value = config.get(key, default)
    return value if isinstance(value, int) and not isinstance(value, bool) else default
