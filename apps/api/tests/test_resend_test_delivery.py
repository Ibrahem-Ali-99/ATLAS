import json
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.audit.models import AuditEvent
from app.domains.campaigns.resend import live_sender
from app.domains.identity.models import MembershipRole
from app.domains.integrations.models import IntegrationConfig
from app.domains.integrations.resend_test import ATTEMPT_LIMIT
from app.domains.integrations.service import open_credentials
from app.integrations.domain_verification import ResendDomainProvider
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login

MESSAGE_ID = "4b0c5e4a-1c2d-4e3f-8a9b-0c1d2e3f4a5b"
SENDING_KEY = "sending-key"


def _admin(client: TestClient, db: Session) -> tuple[str, dict[str, str]]:
    user = make_user(db, "admin@example.com")
    organization = make_organization(db, "Atlas", "atlas-resend")
    make_membership(db, user, organization, MembershipRole.admin)
    session = login(client, "admin@example.com", PASSWORD)
    return str(organization.id), {"X-CSRF-Token": str(session["csrf_token"])}


def _save_email(
    client: TestClient, organization_id: str, headers: dict[str, str], *, key: str = SENDING_KEY
):
    return client.put(
        f"/api/v1/organizations/{organization_id}/integration-configs/email",
        headers=headers,
        json={
            "provider": "smtp",
            "config": {
                "host": "127.0.0.1",
                "port": 1025,
                "from_address": "atlas@localhost",
                "use_tls": False,
                "starttls": False,
            },
            "credentials": json.dumps({"resend_api_key": key}),
            "merge_email_credentials": True,
        },
    )


def _accepted(
    monkeypatch: pytest.MonkeyPatch, *, retrieve: httpx.Response | None = None
) -> list[tuple[str, str, object]]:
    calls: list[tuple[str, str, object]] = []

    def handler(method: str, url: str, **kwargs: object) -> httpx.Response:
        calls.append((method, url, kwargs.get("json")))
        if method == "POST":
            return httpx.Response(200, json={"id": MESSAGE_ID})
        if retrieve is not None:
            return retrieve
        return httpx.Response(401, json={"name": "restricted_api_key", "message": "sending only"})

    monkeypatch.setattr("app.domains.integrations.resend_test.httpx.request", handler)
    return calls


def test_administrator_test_uses_the_official_sender_and_leaves_production_disabled(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization_id, headers = _admin(client, db)
    created = _save_email(client, organization_id, headers)
    assert created.status_code == 200, created.text
    calls = _accepted(monkeypatch)
    response = client.post(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/resend-test",
        headers=headers,
        json={"recipient": "delivered@resend.dev"},
    )
    assert response.status_code == 200, response.text
    assert SENDING_KEY not in response.text
    body = response.json()
    assert body["sender"] == "onboarding@resend.dev"
    assert body["recipient"] == "delivered@resend.dev"
    assert body["message_id"] == MESSAGE_ID
    assert body["provider_confirmation"] == "accepted"
    assert body["status"]["credential_configured"] is True
    assert body["status"]["test_delivery_verified"] is True
    assert body["status"]["sending_domain_verified"] is False
    assert body["status"]["production_delivery_enabled"] is False
    assert calls[0][0] == "POST"
    assert calls[0][1] == "https://api.resend.com/emails"
    sent = calls[0][2]
    assert isinstance(sent, dict)
    assert sent["from"] == "onboarding@resend.dev"
    assert sent["to"] == ["delivered@resend.dev"]
    assert "List-Unsubscribe" not in sent
    db.expire_all()
    record = db.scalar(
        select(IntegrationConfig).where(IntegrationConfig.organization_id == organization_id)
    )
    assert record is not None
    assert record.config["host"] == "127.0.0.1"
    assert record.config["port"] == 1025
    assert record.config["from_address"] == "atlas@localhost"
    stored = json.loads(open_credentials(record) or "{}")
    assert stored["resend_api_key"] == SENDING_KEY
    with pytest.raises(AppError) as blocked:
        live_sender(db, uuid.UUID(organization_id))
    assert blocked.value.code == "campaign_live_disabled"


def test_test_delivery_rejects_an_unapproved_recipient_without_calling_resend(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization_id, headers = _admin(client, db)
    assert _save_email(client, organization_id, headers).is_success
    calls = _accepted(monkeypatch)
    response = client.post(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/resend-test",
        headers=headers,
        json={"recipient": "customer@example.com"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "resend_test_recipient_unapproved"
    assert calls == []


def test_approved_account_owner_can_receive_the_test(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization_id, headers = _admin(client, db)
    created = _save_email(client, organization_id, headers)
    approved = client.put(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/resend-test-recipient",
        headers=headers,
        json={
            "address": "owner@example.com",
            "expected_version": created.json()["credential_version"],
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approved_recipient"] == "owner@example.com"
    _accepted(monkeypatch)
    sent = client.post(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/resend-test",
        headers=headers,
        json={"recipient": "owner@example.com"},
    )
    assert sent.status_code == 200, sent.text
    saved = client.put(
        f"/api/v1/organizations/{organization_id}/integration-configs/email",
        headers=headers,
        json={
            "provider": "smtp",
            "config": {
                "host": "127.0.0.1",
                "port": 1025,
                "from_address": "atlas@localhost",
                "resend_test_recipient": "other@example.com",
            },
            "expected_version": created.json()["credential_version"],
        },
    )
    assert saved.status_code == 200, saved.text
    status = client.get(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/resend-test",
        headers=headers,
    )
    assert status.json()["approved_recipient"] == "owner@example.com"
    assert status.json()["test_delivery_verified"] is True


def test_retrieved_receipt_must_match_the_test_sender_and_recipient(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization_id, headers = _admin(client, db)
    assert _save_email(client, organization_id, headers).is_success
    _accepted(
        monkeypatch,
        retrieve=httpx.Response(
            200,
            json={
                "id": MESSAGE_ID,
                "from": "onboarding@resend.dev",
                "to": ["delivered@resend.dev"],
            },
        ),
    )
    matched = client.post(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/resend-test",
        headers=headers,
        json={"recipient": "delivered@resend.dev"},
    )
    assert matched.status_code == 200, matched.text
    assert matched.json()["provider_confirmation"] == "retrieved"


def test_provider_owner_error_is_actionable_and_does_not_mark_the_test_verified(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization_id, headers = _admin(client, db)
    created = _save_email(client, organization_id, headers)
    approved = client.put(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/resend-test-recipient",
        headers=headers,
        json={
            "address": "owner@example.com",
            "expected_version": created.json()["credential_version"],
        },
    )
    assert approved.is_success

    def handler(method: str, url: str, **kwargs: object) -> httpx.Response:
        del method, url, kwargs
        return httpx.Response(
            422,
            json={
                "name": "validation_error",
                "message": "Only your own email can receive testing emails (owner@example.net).",
            },
        )

    monkeypatch.setattr("app.domains.integrations.resend_test.httpx.request", handler)
    response = client.post(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/resend-test",
        headers=headers,
        json={"recipient": "owner@example.com"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "resend_test_owner_mismatch"
    assert "owner@example.net" in response.json()["error"]["message"]
    assert SENDING_KEY not in response.text
    status = client.get(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/resend-test"
    )
    assert status.json()["test_delivery_verified"] is False
    failed = db.scalar(select(AuditEvent).where(AuditEvent.action == "resend_test_email_failed"))
    assert failed is not None
    assert failed.details["code"] == "resend_test_owner_mismatch"
    assert "resend_api_key" not in failed.details


def test_test_delivery_is_rate_limited(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization_id, headers = _admin(client, db)
    assert _save_email(client, organization_id, headers).is_success
    calls = _accepted(monkeypatch)
    monkeypatch.setattr("app.domains.integrations.resend_test.ATTEMPT_LIMIT", 1)
    monkeypatch.setattr("app.domains.integrations.resend_test.ATTEMPT_GAP", timedelta(0))
    path = f"/api/v1/organizations/{organization_id}/integration-configs/email/resend-test"
    first = client.post(path, headers=headers, json={"recipient": "delivered@resend.dev"})
    second = client.post(path, headers=headers, json={"recipient": "bounced@resend.dev"})
    assert first.status_code == 200, first.text
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "resend_test_rate_limited"
    assert len([call for call in calls if call[0] == "POST"]) == 1
    assert ATTEMPT_LIMIT >= 1


def test_replacing_the_sending_key_clears_test_verification(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization_id, headers = _admin(client, db)
    created = _save_email(client, organization_id, headers)
    _accepted(monkeypatch)
    sent = client.post(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/resend-test",
        headers=headers,
        json={"recipient": "delivered@resend.dev"},
    )
    assert sent.status_code == 200, sent.text
    rotated = client.put(
        f"/api/v1/organizations/{organization_id}/integration-configs/email",
        headers=headers,
        json={
            "provider": "smtp",
            "config": {
                "host": "127.0.0.1",
                "port": 1025,
                "from_address": "atlas@localhost",
            },
            "credentials": json.dumps({"resend_api_key": "replacement-key"}),
            "merge_email_credentials": True,
            "expected_version": created.json()["credential_version"],
        },
    )
    assert rotated.status_code == 200, rotated.text
    status = client.get(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/resend-test"
    )
    assert status.json()["credential_configured"] is True
    assert status.json()["test_delivery_verified"] is False
    assert "replacement-key" not in status.text


def test_staff_and_missing_csrf_cannot_send(client: TestClient, db: Session) -> None:
    user = make_user(db, "staff@example.com")
    organization = make_organization(db, "Atlas", "atlas-staff-resend")
    make_membership(db, user, organization, MembershipRole.staff)
    session = login(client, "staff@example.com", PASSWORD)
    path = f"/api/v1/organizations/{organization.id}/integration-configs/email/resend-test"
    forbidden = client.post(
        path,
        headers={"X-CSRF-Token": str(session["csrf_token"])},
        json={"recipient": "delivered@resend.dev"},
    )
    assert forbidden.status_code == 403
    missing = client.post(path, json={"recipient": "delivered@resend.dev"})
    assert missing.status_code == 403


def test_sending_key_cannot_administer_domains(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(method: str, url: str, **kwargs: object) -> httpx.Response:
        del method, url, kwargs
        return httpx.Response(401, json={"name": "restricted_api_key", "message": "sending only"})

    monkeypatch.setattr("app.integrations.domain_verification.httpx.request", handler)
    with pytest.raises(AppError) as exc:
        ResendDomainProvider(SENDING_KEY).register("example.com")
    assert exc.value.code == "resend_domain_access_required"


def test_receipt_without_a_message_id_is_not_verified(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization_id, headers = _admin(client, db)
    assert _save_email(client, organization_id, headers).is_success

    def handler(method: str, url: str, **kwargs: object) -> httpx.Response:
        del method, url, kwargs
        return httpx.Response(200, json={"object": "email"})

    monkeypatch.setattr("app.domains.integrations.resend_test.httpx.request", handler)
    response = client.post(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/resend-test",
        headers=headers,
        json={"recipient": "complained@resend.dev"},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "resend_receipt_invalid"
    status = client.get(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/resend-test"
    )
    assert status.json()["test_delivery_verified"] is False


def test_administrator_test_does_not_call_campaign_delivery() -> None:
    source = (
        Path(__file__)
        .parents[1]
        .joinpath("app/domains/integrations/resend_test.py")
        .read_text(encoding="utf-8")
    )
    assert "live_sender" not in source
    assert "send_resend" not in source


def test_delivery_feedback_is_a_later_read_and_does_not_send_again(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization_id, headers = _admin(client, db)
    assert _save_email(client, organization_id, headers).is_success
    _accepted(
        monkeypatch,
        retrieve=httpx.Response(
            200,
            json={
                "id": MESSAGE_ID,
                "from": "onboarding@resend.dev",
                "to": ["delivered@resend.dev"],
                "last_event": "sent",
            },
        ),
    )
    sent = client.post(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/resend-test",
        headers=headers,
        json={"recipient": "delivered@resend.dev"},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["provider_confirmation"] == "retrieved"
    assert sent.json()["status"]["provider_last_event"] == "sent"

    calls: list[str] = []

    def handler(method: str, url: str, **kwargs: object) -> httpx.Response:
        del url, kwargs
        calls.append(method)
        return httpx.Response(
            200,
            json={
                "id": MESSAGE_ID,
                "from": "onboarding@resend.dev",
                "to": ["delivered@resend.dev"],
                "last_event": "delivered",
            },
        )

    monkeypatch.setattr("app.domains.integrations.resend_test.httpx.request", handler)
    from app.domains.integrations.resend_test import refresh_delivery

    event = refresh_delivery(db, uuid.UUID(organization_id), attempts=1)
    assert event == "delivered"
    assert calls == ["GET"]
    status = client.get(
        f"/api/v1/organizations/{organization_id}/integration-configs/email/resend-test",
        headers=headers,
    )
    assert status.json()["provider_last_event"] == "delivered"
    assert status.json()["provider_confirmation"] == "retrieved"
