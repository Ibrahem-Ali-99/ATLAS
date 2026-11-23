import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.automation.signatures import open_integration_secret, seal_integration_secret
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType
from app.domains.integrations.schemas import IntegrationInput, IntegrationMetadata


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
    )


def create_configuration(
    db: Session, organization_id: uuid.UUID, data: IntegrationInput, credentials: str | None = None
) -> IntegrationConfig:
    data.validate_provider()
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
    return record


def update_metadata(
    db: Session,
    organization_id: uuid.UUID,
    integration_type: IntegrationType,
    *,
    provider: str,
    config: dict[str, Any],
    expected_version: int,
) -> IntegrationConfig:
    record = _get(db, organization_id, integration_type, lock=True)
    if record is None:
        raise AppError(404, "integration_not_found", "Integration configuration not found")
    data = IntegrationInput(integration_type=integration_type, provider=provider, config=config)
    data.validate_provider()
    if record.credential_version != expected_version:
        raise AppError(
            409,
            "integration_version_conflict",
            "Integration configuration changed; reload before updating",
        )
    record.provider, record.config, record.status = (
        data.provider,
        data.config,
        IntegrationStatus.configured,
    )
    db.flush()
    return record


def replace_credentials(
    db: Session,
    organization_id: uuid.UUID,
    integration_type: IntegrationType,
    credentials: str,
    *,
    expected_version: int,
) -> IntegrationConfig:
    if not credentials.strip():
        raise AppError(422, "credentials_empty", "Credentials cannot be empty")
    record = _get(db, organization_id, integration_type, lock=True)
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
    db.flush()
    return record


def disable_configuration(
    db: Session,
    organization_id: uuid.UUID,
    integration_type: IntegrationType,
    *,
    expected_version: int,
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
    db.flush()
    return record


def revoke_credentials(
    db: Session,
    organization_id: uuid.UUID,
    integration_type: IntegrationType,
    *,
    expected_version: int,
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
    db.flush()
    return record


def open_credentials(record: IntegrationConfig) -> str | None:
    return (
        open_integration_secret(record.encrypted_credentials)
        if record.encrypted_credentials
        else None
    )
