import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.audit.models import AuditEvent
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType
from app.domains.integrations.schemas import IntegrationInput
from app.domains.integrations.service import (
    create_configuration,
    disable_configuration,
    open_credentials,
    read_metadata,
    replace_credentials,
    revoke_credentials,
    safe_metadata,
)
from tests.factories import make_organization


def test_configuration_is_scoped_and_credentials_are_sealed(db: Session) -> None:
    atlas = make_organization(db, "Atlas", "atlas-integrations")
    northwind = make_organization(db, "Northwind", "northwind-integrations")
    record = create_configuration(
        db,
        atlas.id,
        IntegrationInput(
            integration_type="chat",
            provider="groq",
            config={"base_url": "https://api.groq.com/openai/v1"},
        ),
        "gsk-test-secret",
    )
    db.commit()

    assert read_metadata(db, atlas.id, IntegrationType.chat).id == record.id
    assert read_metadata(db, northwind.id, IntegrationType.chat) is None
    stored = db.scalar(select(IntegrationConfig).where(IntegrationConfig.id == record.id))
    assert stored is not None
    assert stored.encrypted_credentials != "gsk-test-secret"
    assert open_credentials(stored) == "gsk-test-secret"
    metadata = safe_metadata(db, atlas.id, IntegrationType.chat)
    assert metadata is not None
    assert metadata.has_credentials is True
    assert not hasattr(metadata, "encrypted_credentials")


def test_replacement_increments_version_and_disable_is_explicit(db: Session) -> None:
    organization = make_organization(db, "Atlas", "atlas-rotation")
    create_configuration(
        db, organization.id, IntegrationInput(integration_type="n8n", provider="n8n"), "old-secret"
    )
    db.commit()
    replaced = replace_credentials(
        db, organization.id, IntegrationType.n8n, "new-secret", expected_version=1
    )
    disable_configuration(
        db, organization.id, IntegrationType.n8n, expected_version=replaced.credential_version
    )
    db.commit()
    assert replaced.credential_version == 2
    assert replaced.status == IntegrationStatus.disabled
    assert open_credentials(replaced) == "new-secret"
    revoked = revoke_credentials(
        db,
        organization.id,
        IntegrationType.n8n,
        expected_version=replaced.credential_version,
    )
    db.commit()
    assert revoked.credential_version == 3
    assert revoked.status == IntegrationStatus.disabled
    assert open_credentials(revoked) is None
    actions = db.scalars(
        select(AuditEvent.action)
        .where(AuditEvent.organization_id == organization.id)
        .order_by(AuditEvent.created_at, AuditEvent.id)
    ).all()
    assert sorted(actions) == sorted([
        "integration_configuration_created",
        "integration_credentials_replaced",
        "integration_configuration_disabled",
        "integration_credentials_revoked",
    ])


def test_invalid_provider_and_stale_update_are_rejected(db: Session) -> None:
    organization = make_organization(db, "Atlas", "atlas-validation")
    invalid = IntegrationInput(integration_type="chat", provider="ollama")
    with pytest.raises(ValueError):
        invalid.validate_provider()
    record = create_configuration(
        db, organization.id, IntegrationInput(integration_type="chat", provider="openai"), "secret"
    )
    db.commit()
    with pytest.raises(AppError) as exc:
        replace_credentials(
            db,
            organization.id,
            IntegrationType.chat,
            "other",
            expected_version=record.credential_version + 1,
        )
    assert exc.value.code == "integration_version_conflict"


def test_wrong_encryption_key_fails_closed(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.domains.automation import signatures

    organization = make_organization(db, "Atlas", "atlas-key-failure")
    record = create_configuration(
        db, organization.id, IntegrationInput(integration_type="chat", provider="groq"), "secret"
    )
    db.commit()
    wrong = get_settings().model_copy(
        update={"secret_key": "not-the-configured-key"}
    )
    monkeypatch.setattr(signatures, "get_settings", lambda: wrong)
    with pytest.raises(AppError) as exc:
        open_credentials(record)
    assert exc.value.code == "integration_secret_invalid"
