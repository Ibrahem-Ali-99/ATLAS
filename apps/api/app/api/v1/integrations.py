"""Administrator APIs for organization-scoped integration configuration."""
# ruff: noqa: E501

import json
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter
from sqlalchemy import select

from app.core.errors import AppError
from app.domains.audit.service import record_event
from app.domains.automation.signatures import open_integration_secret
from app.domains.identity.dependencies import Admin, CsrfAdmin, DbSession
from app.domains.integrations.domain_models import EmailDomainVerification
from app.domains.integrations.domain_service import check_domain, register_domain, revoke_domain
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType
from app.domains.integrations.schemas import (
    CredentialUpdate,
    EmailDomainInput,
    EmailDomainOut,
    IntegrationInput,
    IntegrationMetadata,
    IntegrationUpdate,
    VerificationResult,
    VersionUpdate,
)
from app.domains.integrations.service import (
    disable_configuration,
    enable_configuration,
    read_metadata,
    replace_configuration,
    replace_credentials,
    revoke_credentials,
    safe_metadata,
    update_metadata,
)
from app.integrations.language import get_chat_client, get_embedding_client
from app.integrations.smtp_verification import verify_smtp

router = APIRouter(
    prefix="/organizations/{organization_id}/integration-configs", tags=["integrations"]
)


@router.post("/email-domains", response_model=EmailDomainOut)
def create_email_domain(
    body: EmailDomainInput, admin: CsrfAdmin, db: DbSession
) -> EmailDomainVerification:
    record = register_domain(db, admin.organization.id, body.domain)
    record_event(
        db,
        admin.organization.id,
        "email_domain_registered",
        {"domain": record.domain},
        actor_id=admin.user.id,
    )
    db.commit()
    return record


@router.get("/email-domains", response_model=list[EmailDomainOut])
def list_email_domains(admin: Admin, db: DbSession) -> list[EmailDomainVerification]:
    return list(
        db.scalars(
            select(EmailDomainVerification)
            .where(EmailDomainVerification.organization_id == admin.organization.id)
            .order_by(EmailDomainVerification.domain)
        ).all()
    )


@router.get("/email-domains/{domain_id}", response_model=EmailDomainOut)
def get_email_domain(domain_id: uuid.UUID, admin: Admin, db: DbSession) -> EmailDomainVerification:
    record = db.scalar(
        select(EmailDomainVerification).where(
            EmailDomainVerification.id == domain_id,
            EmailDomainVerification.organization_id == admin.organization.id,
        )
    )
    if record is None:
        raise AppError(404, "domain_not_found", "Sending domain not found")
    return record


@router.post("/email-domains/{domain_id}/check", response_model=EmailDomainOut)
def verify_email_domain(
    domain_id: uuid.UUID, admin: CsrfAdmin, db: DbSession
) -> EmailDomainVerification:
    record = db.scalar(
        select(EmailDomainVerification).where(
            EmailDomainVerification.id == domain_id,
            EmailDomainVerification.organization_id == admin.organization.id,
        )
    )
    if record is None:
        raise AppError(404, "domain_not_found", "Sending domain not found")
    check_domain(db, record)
    record_event(
        db,
        admin.organization.id,
        "email_domain_verification_checked",
        {"domain": record.domain},
        actor_id=admin.user.id,
    )
    if record.status == "verified":
        record_event(
            db,
            admin.organization.id,
            "email_domain_verified",
            {"domain": record.domain},
            actor_id=admin.user.id,
        )
    db.commit()
    return record


@router.post("/email-domains/{domain_id}/revoke", response_model=EmailDomainOut)
def revoke_email_domain(
    domain_id: uuid.UUID, admin: CsrfAdmin, db: DbSession
) -> EmailDomainVerification:
    record = db.scalar(
        select(EmailDomainVerification).where(
            EmailDomainVerification.id == domain_id,
            EmailDomainVerification.organization_id == admin.organization.id,
        )
    )
    if record is None:
        raise AppError(404, "domain_not_found", "Sending domain not found")
    revoke_domain(db, record)
    record_event(
        db,
        admin.organization.id,
        "email_domain_revoked",
        {"domain": record.domain},
        actor_id=admin.user.id,
    )
    db.commit()
    return record


@router.get("", response_model=list[IntegrationMetadata])
def list_integrations(
    organization_id: uuid.UUID, admin: Admin, db: DbSession
) -> list[IntegrationMetadata]:
    del organization_id
    rows = db.scalars(
        select(IntegrationConfig.integration_type)
        .where(IntegrationConfig.organization_id == admin.organization.id)
        .order_by(IntegrationConfig.integration_type)
    ).all()
    result: list[IntegrationMetadata] = []
    for kind in rows:
        metadata = safe_metadata(db, admin.organization.id, kind)
        if metadata is not None:
            result.append(metadata)
    return result


@router.get("/{integration_type}", response_model=IntegrationMetadata | None)
def get_integration(
    integration_type: IntegrationType, admin: Admin, db: DbSession
) -> IntegrationMetadata | None:
    return safe_metadata(db, admin.organization.id, integration_type)


@router.put("/{integration_type}", response_model=IntegrationMetadata)
def put_integration(
    integration_type: IntegrationType,
    body: IntegrationUpdate,
    admin: CsrfAdmin,
    db: DbSession,
) -> IntegrationMetadata:
    data = IntegrationInput(
        integration_type=integration_type,
        provider=body.provider,
        config=body.config,
        credentials=body.credentials,
    )
    record = replace_configuration(
        db,
        admin.organization.id,
        data,
        expected_version=body.expected_version,
        actor_id=admin.user.id,
    )
    db.commit()
    return safe_metadata(db, admin.organization.id, record.integration_type)  # type: ignore[return-value]


@router.post("/{integration_type}/credentials", response_model=IntegrationMetadata)
def put_credentials(
    integration_type: IntegrationType,
    body: CredentialUpdate,
    admin: CsrfAdmin,
    db: DbSession,
) -> IntegrationMetadata:
    record = replace_credentials(
        db,
        admin.organization.id,
        integration_type,
        body.credentials,
        expected_version=body.expected_version,
        actor_id=admin.user.id,
    )
    db.commit()
    return safe_metadata(db, admin.organization.id, record.integration_type)  # type: ignore[return-value]


@router.patch("/{integration_type}", response_model=IntegrationMetadata)
def patch_integration(
    integration_type: IntegrationType,
    body: IntegrationUpdate,
    admin: CsrfAdmin,
    db: DbSession,
) -> IntegrationMetadata:
    record = update_metadata(
        db,
        admin.organization.id,
        integration_type,
        provider=body.provider,
        config=body.config,
        expected_version=body.expected_version or 0,
        actor_id=admin.user.id,
    )
    db.commit()
    return safe_metadata(db, admin.organization.id, record.integration_type)  # type: ignore[return-value]


@router.post("/{integration_type}/disable", response_model=IntegrationMetadata)
def disable(
    integration_type: IntegrationType, body: VersionUpdate, admin: CsrfAdmin, db: DbSession
) -> IntegrationMetadata:
    record = disable_configuration(
        db,
        admin.organization.id,
        integration_type,
        expected_version=body.expected_version,
        actor_id=admin.user.id,
    )
    db.commit()
    return safe_metadata(db, admin.organization.id, record.integration_type)  # type: ignore[return-value]


@router.post("/{integration_type}/enable", response_model=IntegrationMetadata)
def enable(
    integration_type: IntegrationType, body: VersionUpdate, admin: CsrfAdmin, db: DbSession
) -> IntegrationMetadata:
    record = enable_configuration(
        db,
        admin.organization.id,
        integration_type,
        expected_version=body.expected_version,
        actor_id=admin.user.id,
    )
    db.commit()
    return safe_metadata(db, admin.organization.id, record.integration_type)  # type: ignore[return-value]


@router.post("/{integration_type}/revoke", response_model=IntegrationMetadata)
def revoke(
    integration_type: IntegrationType, body: VersionUpdate, admin: CsrfAdmin, db: DbSession
) -> IntegrationMetadata:
    record = revoke_credentials(
        db,
        admin.organization.id,
        integration_type,
        expected_version=body.expected_version,
        actor_id=admin.user.id,
    )
    db.commit()
    return safe_metadata(db, admin.organization.id, record.integration_type)  # type: ignore[return-value]


@router.post("/{integration_type}/verify", response_model=VerificationResult)
def verify(
    integration_type: IntegrationType, admin: CsrfAdmin, db: DbSession
) -> VerificationResult:
    record = read_metadata(db, admin.organization.id, integration_type)
    if record is None:
        raise AppError(404, "integration_not_found", "Integration configuration not found")
    metadata = safe_metadata(db, admin.organization.id, integration_type)
    assert metadata is not None
    try:
        if integration_type == IntegrationType.chat:
            get_chat_client(db, admin.organization.id).complete(
                "Respond with one short word.", "verification"
            )
        elif integration_type == IntegrationType.embedding:
            get_embedding_client(db, admin.organization.id).embed(
                ["ATLAS integration verification"]
            )
        elif integration_type == IntegrationType.email:
            if record.status == IntegrationStatus.disabled:
                raise AppError(409, "integration_disabled", "Email integration is disabled.")
            credentials = (
                open_integration_secret(record.encrypted_credentials)
                if record.encrypted_credentials
                else ""
            )
            try:
                credential_data = json.loads(credentials)
            except json.JSONDecodeError:
                credential_data = {}
            username = (
                credential_data.get("username") if isinstance(credential_data, dict) else None
            )
            password = (
                credential_data.get("password") if isinstance(credential_data, dict) else None
            )
            result = verify_smtp(
                host=str(record.config.get("host", "")),
                port=int(record.config.get("port", 0)),
                username=username if isinstance(username, str) else None,
                password=password if isinstance(password, str) else None,
                starttls=bool(record.config.get("starttls", False)),
                use_tls=bool(record.config.get("use_tls", False)),
            )
            if not result.verified:
                raise AppError(502, "smtp_verification_failed", result.detail)
        elif integration_type == IntegrationType.whatsapp:
            credentials = open_integration_secret(record.encrypted_credentials or "")
            try:
                credential_data = json.loads(credentials)
            except json.JSONDecodeError as exc:
                raise AppError(
                    422, "whatsapp_credentials_invalid", "WhatsApp credentials are invalid"
                ) from exc
            token = (
                credential_data.get("access_token") if isinstance(credential_data, dict) else None
            )
            phone_id = record.config.get("phone_number_id")
            if (
                not isinstance(token, str)
                or not token
                or not isinstance(phone_id, str)
                or not phone_id
            ):
                raise AppError(
                    422,
                    "whatsapp_configuration_incomplete",
                    "WhatsApp phone number ID and access token are required",
                )
            try:
                response = httpx.get(
                    f"https://graph.facebook.com/v21.0/{phone_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10.0,
                )
            except httpx.TimeoutException as exc:
                raise AppError(
                    504, "whatsapp_provider_timeout", "WhatsApp connection test timed out"
                ) from exc
            if response.status_code >= 400:
                raise AppError(
                    502, "whatsapp_provider_error", "WhatsApp rejected the connection test"
                )
        else:
            raise AppError(
                422, "verification_unsupported", "This integration has no provider test."
            )
    except AppError as exc:
        record.status = IntegrationStatus.verification_failed
        record.verified_at = datetime.now(UTC)
        record.verification_detail = exc.message[:500]
        record_event(
            db,
            admin.organization.id,
            "integration_verification_status_changed",
            {"integration_type": integration_type.value, "verified": False},
            actor_id=admin.user.id,
        )
        db.commit()
        metadata = safe_metadata(db, admin.organization.id, integration_type)
        assert metadata is not None
        return VerificationResult(
            integration=metadata,
            verified=False,
            detail=exc.message,
        )
    record.status = IntegrationStatus.configured
    record.verified_at = datetime.now(UTC)
    record.verification_detail = "Provider verification succeeded."
    record_event(
        db,
        admin.organization.id,
        "integration_verification_status_changed",
        {"integration_type": integration_type.value, "verified": True},
        actor_id=admin.user.id,
    )
    db.commit()
    metadata = safe_metadata(db, admin.organization.id, integration_type)
    assert metadata is not None
    return VerificationResult(
        integration=metadata,
        verified=True,
        detail="Provider verification succeeded.",
    )
