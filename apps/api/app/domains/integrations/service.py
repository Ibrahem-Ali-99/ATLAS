import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.audit.service import record_event
from app.domains.automation.signatures import open_integration_secret, seal_integration_secret
from app.domains.inbox.models import InboxMessage
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType
from app.domains.integrations.resend_credentials import (
    email_credentials_for_storage,
    retain_test_recipient,
)
from app.domains.integrations.schemas import IntegrationInput, IntegrationMetadata
from app.domains.knowledge.models import Chunk, Document, DocumentStatus
from app.domains.knowledge.vectors import lock_embedding_index


def _get(
    db: Session,
    organization_id: uuid.UUID,
    integration_type: IntegrationType,
    *,
    lock: bool = False,
) -> IntegrationConfig | None:
    query = select(IntegrationConfig).where(
        IntegrationConfig.organization_id == organization_id,
        IntegrationConfig.integration_type == integration_type,
    )
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


def read_metadata(
    db: Session, organization_id: uuid.UUID, integration_type: IntegrationType
) -> IntegrationConfig | None:
    return _get(db, organization_id, integration_type)


def safe_metadata(
    db: Session, organization_id: uuid.UUID, integration_type: IntegrationType
) -> IntegrationMetadata | None:
    record = read_metadata(db, organization_id, integration_type)
    if record is None:
        return None
    last_inbound_at = None
    if (
        integration_type == IntegrationType.whatsapp
        and record.status == IntegrationStatus.configured
    ):
        last_inbound_at = db.scalar(
            select(func.max(InboxMessage.created_at)).where(
                InboxMessage.organization_id == organization_id,
                InboxMessage.channel == "whatsapp",
                InboxMessage.direction == "inbound",
                InboxMessage.recipient == record.config.get("phone_number_id"),
            )
        )
    if integration_type == IntegrationType.email and record.status == IntegrationStatus.configured:
        sender_address = record.config.get("from_address")
        if isinstance(sender_address, str):
            last_inbound_at = db.scalar(
                select(func.max(InboxMessage.created_at)).where(
                    InboxMessage.organization_id == organization_id,
                    InboxMessage.channel == "email",
                    InboxMessage.direction == "inbound",
                    InboxMessage.recipient == sender_address.strip().casefold(),
                )
            )
    return IntegrationMetadata(
        id=str(record.id),
        organization_id=str(record.organization_id),
        integration_type=record.integration_type,
        provider=record.provider,
        config=record.config,
        status=record.status,
        credential_version=record.credential_version,
        has_credentials=bool(record.encrypted_credentials),
        created_at=record.created_at,
        updated_at=record.updated_at,
        verified_at=record.verified_at,
        verification_detail=record.verification_detail,
        last_inbound_at=last_inbound_at,
    )


def create_configuration(
    db: Session,
    organization_id: uuid.UUID,
    data: IntegrationInput,
    credentials: str | None = None,
    *,
    actor_id: uuid.UUID | None = None,
) -> IntegrationConfig:
    data.validate_provider()
    _validate_embedding_config(data)
    if _get(db, organization_id, data.integration_type) is not None:
        raise AppError(
            409,
            "integration_exists",
            "This integration type is already configured for the organization",
        )
    record = IntegrationConfig(
        organization_id=organization_id,
        integration_type=data.integration_type,
        provider=data.provider,
        config=data.config,
        encrypted_credentials=seal_integration_secret(credentials) if credentials else None,
    )
    db.add(record)
    db.flush()
    record_event(
        db,
        organization_id,
        "integration_configuration_created",
        {
            "integration_type": data.integration_type.value,
            "provider": data.provider,
            "credential_version": record.credential_version,
            "has_credentials": bool(credentials),
        },
        actor_id=actor_id,
    )
    return record


def replace_configuration(
    db: Session,
    organization_id: uuid.UUID,
    data: IntegrationInput,
    *,
    expected_version: int | None = None,
    actor_id: uuid.UUID | None = None,
    merge_email_credentials: bool = False,
) -> IntegrationConfig:
    """Create or atomically replace one organization integration."""
    if data.integration_type == IntegrationType.embedding:
        lock_embedding_index(db, organization_id)
    existing = _get(db, organization_id, data.integration_type, lock=True)
    if data.integration_type == IntegrationType.embedding:
        _guard_embedding_change(db, organization_id, existing, data)
    if data.integration_type == IntegrationType.email:
        current_config = None if existing is None else existing.config
        data = data.model_copy(
            update={"config": retain_test_recipient(current_config, data.config)}
        )
        if data.credentials is not None:
            data = data.model_copy(
                update={
                    "credentials": email_credentials_for_storage(
                        existing,
                        data.credentials,
                        merge=merge_email_credentials,
                    )
                }
            )
        elif merge_email_credentials:
            raise AppError(422, "invalid_credential_update", "Supply email credentials to update")
    elif merge_email_credentials:
        raise AppError(422, "invalid_credential_update", "Supply email credentials to update")
    if existing is None:
        return create_configuration(
            db,
            organization_id,
            data,
            data.credentials,
            actor_id=actor_id,
        )
    if expected_version is None or existing.credential_version != expected_version:
        raise AppError(
            409,
            "integration_version_conflict",
            "Integration configuration changed; reload before updating",
        )
    provider_changed = existing.provider != data.provider
    config_changed = existing.config != data.config
    existing.provider = data.provider
    existing.config = data.config
    _validate_embedding_config(data)
    if data.credentials is not None:
        existing.encrypted_credentials = seal_integration_secret(data.credentials)
        existing.credential_version += 1
    elif provider_changed or config_changed:
        if provider_changed:
            existing.encrypted_credentials = None
        existing.credential_version += 1
    existing.status = IntegrationStatus.configured
    existing.verified_at = None
    existing.verification_detail = None
    db.flush()
    record_event(
        db,
        organization_id,
        "integration_provider_changed",
        {
            "integration_type": data.integration_type.value,
            "provider": data.provider,
            "credential_version": existing.credential_version,
            "provider_changed": provider_changed,
        },
        actor_id=actor_id,
    )
    return existing


def _config_text(config: Mapping[str, Any], key: str) -> str:
    value = config.get(key)
    return value.strip() if isinstance(value, str) else ""


def _config_dimensions(config: Mapping[str, Any]) -> int | None:
    value = config.get("dimensions")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _validate_embedding_config(data: IntegrationInput) -> None:
    if data.integration_type != IntegrationType.embedding:
        return
    dimensions = data.config.get("dimensions")
    if dimensions is not None and dimensions not in {768, 1536}:
        raise AppError(
            422,
            "embedding_dimensions_invalid",
            "Embedding dimensions must be 768 or 1536",
        )


def _has_ready_chunks(db: Session, organization_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(Chunk.id)
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Chunk.organization_id == organization_id,
                Document.status == DocumentStatus.ready,
            )
            .limit(1)
        )
        is not None
    )


def _guard_embedding_change(
    db: Session,
    organization_id: uuid.UUID,
    existing: IntegrationConfig | None,
    data: IntegrationInput,
) -> None:
    settings = get_settings()

    def signature(provider: str, config: Mapping[str, Any]) -> tuple[str, str, str, int]:
        return (
            provider,
            (_config_text(config, "base_url") or settings.embedding_base_url).rstrip("/"),
            _config_text(config, "model") or settings.embedding_model,
            _config_dimensions(config) or settings.embedding_dimensions,
        )

    before = (
        signature(existing.provider, existing.config)
        if existing
        else signature(settings.embedding_provider, {})
    )
    if before != signature(data.provider, data.config) and _has_ready_chunks(db, organization_id):
        raise AppError(
            409,
            "embedding_reindex_required",
            "Build a replacement index before changing the embedding configuration.",
        )


def update_metadata(
    db: Session,
    organization_id: uuid.UUID,
    integration_type: IntegrationType,
    *,
    provider: str,
    config: dict[str, Any],
    expected_version: int,
    actor_id: uuid.UUID | None = None,
) -> IntegrationConfig:
    if integration_type == IntegrationType.embedding:
        lock_embedding_index(db, organization_id)
    record = _get(db, organization_id, integration_type, lock=True)
    if record is None:
        raise AppError(404, "integration_not_found", "Integration configuration not found")
    if integration_type == IntegrationType.email:
        config = retain_test_recipient(record.config, config)
    data = IntegrationInput(integration_type=integration_type, provider=provider, config=config)
    data.validate_provider()
    _validate_embedding_config(data)
    if integration_type == IntegrationType.embedding:
        _guard_embedding_change(db, organization_id, record, data)
    if record.credential_version != expected_version:
        raise AppError(
            409,
            "integration_version_conflict",
            "Integration configuration changed; reload before updating",
        )
    provider_changed = record.provider != data.provider
    if provider_changed:
        record.encrypted_credentials = None
    record.provider, record.config, record.status = (
        data.provider,
        data.config,
        IntegrationStatus.configured,
    )
    record.credential_version += 1
    record.verified_at = None
    record.verification_detail = None
    db.flush()
    record_event(
        db,
        organization_id,
        "integration_provider_changed",
        {
            "integration_type": integration_type.value,
            "provider": data.provider,
            "credential_version": record.credential_version,
            "provider_changed": provider_changed,
        },
        actor_id=actor_id,
    )
    return record


def replace_credentials(
    db: Session,
    organization_id: uuid.UUID,
    integration_type: IntegrationType,
    credentials: str,
    *,
    expected_version: int,
    actor_id: uuid.UUID | None = None,
) -> IntegrationConfig:
    if not credentials.strip():
        raise AppError(422, "credentials_empty", "Credentials cannot be empty")
    record = _get(db, organization_id, integration_type, lock=True)
    if record is not None and integration_type == IntegrationType.email:
        credentials = email_credentials_for_storage(record, credentials, merge=False)
    if record is None:
        raise AppError(404, "integration_not_found", "Integration configuration not found")
    if record.credential_version != expected_version:
        raise AppError(
            409,
            "integration_version_conflict",
            "Integration configuration changed; reload before updating",
        )
    record.encrypted_credentials = seal_integration_secret(credentials)
    record.credential_version += 1
    record.status = IntegrationStatus.configured
    record.verified_at = None
    record.verification_detail = None
    db.flush()
    record_event(
        db,
        organization_id,
        "integration_credentials_replaced",
        {
            "integration_type": integration_type.value,
            "credential_version": record.credential_version,
        },
        actor_id=actor_id,
    )
    return record


def disable_configuration(
    db: Session,
    organization_id: uuid.UUID,
    integration_type: IntegrationType,
    *,
    expected_version: int,
    actor_id: uuid.UUID | None = None,
) -> IntegrationConfig:
    record = _get(db, organization_id, integration_type, lock=True)
    if record is None:
        raise AppError(404, "integration_not_found", "Integration configuration not found")
    if record.credential_version != expected_version:
        raise AppError(
            409,
            "integration_version_conflict",
            "Integration configuration changed; reload before updating",
        )
    record.status = IntegrationStatus.disabled
    record.verified_at = None
    record.verification_detail = None
    db.flush()
    record_event(
        db,
        organization_id,
        "integration_configuration_disabled",
        {
            "integration_type": integration_type.value,
            "credential_version": record.credential_version,
        },
        actor_id=actor_id,
    )
    return record


def revoke_credentials(
    db: Session,
    organization_id: uuid.UUID,
    integration_type: IntegrationType,
    *,
    expected_version: int,
    actor_id: uuid.UUID | None = None,
) -> IntegrationConfig:
    record = _get(db, organization_id, integration_type, lock=True)
    if record is None:
        raise AppError(404, "integration_not_found", "Integration configuration not found")
    if record.credential_version != expected_version:
        raise AppError(
            409,
            "integration_version_conflict",
            "Integration configuration changed; reload before updating",
        )
    record.encrypted_credentials = None
    record.credential_version += 1
    record.status = IntegrationStatus.disabled
    record.verified_at = None
    record.verification_detail = None
    db.flush()
    record_event(
        db,
        organization_id,
        "integration_credentials_revoked",
        {
            "integration_type": integration_type.value,
            "credential_version": record.credential_version,
        },
        actor_id=actor_id,
    )
    return record


def enable_configuration(
    db: Session,
    organization_id: uuid.UUID,
    integration_type: IntegrationType,
    *,
    expected_version: int,
    actor_id: uuid.UUID | None = None,
) -> IntegrationConfig:
    record = _get(db, organization_id, integration_type, lock=True)
    if record is None:
        raise AppError(404, "integration_not_found", "Integration configuration not found")
    if record.credential_version != expected_version:
        raise AppError(
            409,
            "integration_version_conflict",
            "Integration configuration changed; reload before updating",
        )
    record.status = IntegrationStatus.configured
    db.flush()
    record_event(
        db,
        organization_id,
        "integration_configuration_enabled",
        {
            "integration_type": integration_type.value,
            "credential_version": record.credential_version,
        },
        actor_id=actor_id,
    )
    return record


def open_credentials(record: IntegrationConfig) -> str | None:
    return (
        open_integration_secret(record.encrypted_credentials)
        if record.encrypted_credentials
        else None
    )
