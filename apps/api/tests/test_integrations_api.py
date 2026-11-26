import json

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.identity.models import MembershipRole
from app.domains.integrations.models import IntegrationConfig
from app.domains.integrations.service import open_credentials
from app.integrations.smtp_verification import verify_smtp
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login


def _admin(client: TestClient, db: Session) -> tuple[str, dict[str, str]]:
    user = make_user(db, "admin@example.com")
    organization = make_organization(db, "Atlas", "atlas-api")
    make_membership(db, user, organization, MembershipRole.admin)
    session = login(client, "admin@example.com", PASSWORD)
    return str(organization.id), {"X-CSRF-Token": str(session["csrf_token"])}


def test_admin_can_configure_without_returning_secret(client: TestClient, db: Session) -> None:
    organization_id, headers = _admin(client, db)
    response = client.put(
        f"/api/v1/organizations/{organization_id}/integration-configs/chat",
        json={
            "provider": "groq",
            "config": {"base_url": "https://api.groq.com/openai/v1", "model": "test"},
            "credentials": "gsk-test-secret",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["has_credentials"] is True
    assert "gsk-test-secret" not in response.text


def test_integration_mutation_requires_csrf(client: TestClient, db: Session) -> None:
    organization_id, _ = _admin(client, db)
    response = client.put(
        f"/api/v1/organizations/{organization_id}/integration-configs/chat",
        json={"provider": "groq", "credentials": "secret"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


def test_non_admin_cannot_modify_integration(client: TestClient, db: Session) -> None:
    user = make_user(db, "staff@example.com")
    organization = make_organization(db, "Atlas", "atlas-staff")
    make_membership(db, user, organization, MembershipRole.staff)
    session = login(client, "staff@example.com", PASSWORD)
    response = client.put(
        f"/api/v1/organizations/{organization.id}/integration-configs/chat",
        json={"provider": "groq", "credentials": "secret"},
        headers={"X-CSRF-Token": str(session["csrf_token"])},
    )
    assert response.status_code == 403


def test_email_credentials_can_be_updated_independently(client: TestClient, db: Session) -> None:
    organization_id, headers = _admin(client, db)
    path = f"/api/v1/organizations/{organization_id}/integration-configs/email"
    payload = {
        "provider": "smtp",
        "config": {
            "host": "smtp.example.test",
            "port": 587,
            "starttls": True,
            "from_address": "noreply@example.test",
        },
        "merge_email_credentials": True,
    }
    created = client.put(
        path, headers=headers, json={**payload, "credentials": '{"resend_api_key":"domain-token"}'}
    )
    assert created.is_success
    updated = client.put(
        path,
        headers=headers,
        json={
            **payload,
            "expected_version": created.json()["credential_version"],
            "credentials": '{"username":"smtp-user","password":"smtp-pass"}',
        },
    )
    assert updated.is_success
    assert "smtp-pass" not in updated.text
    record = db.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == organization_id,
        )
    )
    assert record is not None
    assert json.loads(open_credentials(record) or "{}") == {
        "resend_api_key": "domain-token",
        "username": "smtp-user",
        "password": "smtp-pass",
    }
    result = verify_smtp(
        host="smtp.example.test",
        port=25,
        username="smtp-user",
        password="smtp-pass",
        use_tls=False,
        starttls=False,
    )
    assert not result.verified
    assert "TLS" in result.detail


def test_email_configuration_is_encrypted_and_verification_is_bounded(
    client: TestClient, db: Session, monkeypatch
) -> None:
    organization_id, headers = _admin(client, db)
    response = client.put(
        f"/api/v1/organizations/{organization_id}/integration-configs/email",
        json={
            "provider": "smtp",
            "config": {
                "host": "smtp.example.test",
                "port": 587,
                "starttls": True,
                "use_tls": False,
                "from_address": "ATLAS <noreply@example.test>",
                "reply_to": "support@example.test",
            },
            "credentials": '{"username":"smtp-user","password":"smtp-password"}',
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert "smtp-password" not in response.text
    record = db.scalar(
        select(IntegrationConfig).where(IntegrationConfig.organization_id == organization_id)
    )
    assert record is not None
    assert record.encrypted_credentials is not None
    assert "smtp-password" not in record.encrypted_credentials

    monkeypatch.setattr(
        "app.api.v1.integrations.verify_smtp",
        lambda **_: type("Result", (), {"verified": True, "detail": "connection ok"})(),
    )
    checked = client.post(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/verify",
        headers=headers,
    )
    assert checked.status_code == 200, checked.text
    assert checked.json()["verified"] is True
    assert checked.json()["integration"]["verified_at"] is not None


def test_disabled_email_configuration_fails_closed(client: TestClient, db: Session) -> None:
    organization_id, headers = _admin(client, db)
    created = client.put(
        f"/api/v1/organizations/{organization_id}/integration-configs/email",
        json={
            "provider": "smtp",
            "config": {"host": "smtp.example.test", "port": 587, "from_address": "a@example.test"},
            "credentials": '{"username":"u","password":"p"}',
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    version = created.json()["credential_version"]
    disabled = client.post(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/disable",
        json={"expected_version": version},
        headers=headers,
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
