import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.approvals.service import execute_approved
from app.domains.crm import service as crm
from app.domains.identity.models import MembershipRole
from app.domains.inbox.models import InboxConversation, InboxMessage
from app.domains.integrations import whatsapp_test
from app.domains.integrations.models import IntegrationConfig, IntegrationType
from app.integrations import whatsapp
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf


def _graph(monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]) -> None:
    def get(address: str, **_options: object) -> httpx.Response:
        assert address.endswith("/123456")
        assert "messages" not in address
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(whatsapp_test.httpx, "get", get)


def test_restricted_test_reply_sends_once_without_enabling_customer_messaging(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = make_organization(db, "Test reply", "whatsapp-test-reply")
    admin = make_user(db, "whatsapp-test-admin@example.com")
    staff = make_user(db, "whatsapp-test-staff@example.com")
    make_membership(db, admin, org, MembershipRole.admin)
    make_membership(db, staff, org, MembershipRole.staff)
    headers = _csrf(login(client, admin.email, PASSWORD))
    url = f"/api/v1/organizations/{org.id}/integration-configs/whatsapp"
    saved = client.put(
        url,
        headers=headers,
        json={
            "provider": "meta",
            "config": {"business_account_id": "12345", "phone_number_id": "123456"},
            "credentials": json.dumps({"access_token": "disposable-meta-token"}),
        },
    )
    assert saved.status_code == 200, saved.text
    version = saved.json()["credential_version"]
    monkeypatch.setattr(
        "app.api.v1.integrations.httpx.get",
        lambda *_args, **_kwargs: httpx.Response(200, json={"id": "123456"}),
    )
    assert client.post(f"{url}/verify", headers=headers).json()["verified"]
    secret = "disposable-callback-signing-secret"
    monkeypatch.setattr(get_settings(), "whatsapp_webhook_app_secret", secret)
    body = json.dumps(
        {
            "entry": [
                {
                    "id": "12345",
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "123456"},
                                "messages": [
                                    {
                                        "type": "text",
                                        "id": "wamid.inbound",
                                        "from": "15551234567",
                                        "text": {"body": "I would like to book an appointment."},
                                    }
                                ],
                            }
                        }
                    ],
                }
            ]
        }
    ).encode()
    signed = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    accepted = client.post(
        f"/api/v1/organizations/{org.id}/inbox/webhooks/whatsapp",
        content=body,
        headers={"x-hub-signature-256": signed},
    )
    assert accepted.json()["accepted"] == 1
    conversation_id = db.scalar(
        select(InboxMessage.conversation_id).where(InboxMessage.organization_id == org.id)
    )
    thread_url = f"/api/v1/organizations/{org.id}/inbox/{conversation_id}"
    assert "replies are disabled" in client.get(thread_url).json()["reply_unavailable"]
    recipient_url = (
        f"/api/v1/organizations/{org.id}/integration-configs/whatsapp/test-reply-recipient"
    )
    staff_headers = _csrf(login(client, staff.email, PASSWORD))
    assert (
        client.put(
            recipient_url,
            headers=staff_headers,
            json={"phone": "+1 555 123 4567", "expected_version": version},
        ).status_code
        == 403
    )
    headers = _csrf(login(client, admin.email, PASSWORD))
    unknown = client.put(
        recipient_url,
        headers=headers,
        json={"phone": "+1 555 000 1111", "expected_version": version},
    )
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "whatsapp_test_recipient_unknown"
    _graph(monkeypatch, {"id": "123456", "verified_name": "Acme", "account_mode": "LIVE"})
    production_number = client.put(
        recipient_url,
        headers=headers,
        json={"phone": "+1 (555) 123-4567", "expected_version": version},
    )
    assert production_number.status_code == 409
    assert production_number.json()["error"]["code"] == "whatsapp_test_number_required"
    _graph(monkeypatch, {"id": "123456", "verified_name": "Test Number", "account_mode": "SANDBOX"})
    approved = client.put(
        recipient_url,
        headers=headers,
        json={"phone": "+1 (555) 123-4567", "expected_version": version},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["recipient_suffix"] == "4567"
    assert approved.json()["production_messaging_enabled"] is False
    assert "15551234567" not in approved.text
    db.expire_all()
    record = db.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == org.id,
            IntegrationConfig.integration_type == IntegrationType.whatsapp,
        )
    )
    assert record is not None
    assert record.credential_version == version
    assert record.verified_at is not None
    listed = client.get(
        f"/api/v1/organizations/{org.id}/integration-configs", headers=headers
    )
    assert "15551234567" not in listed.text
    assert "whatsapp_test_recipient" not in listed.text
    contact = client.post(
        f"{thread_url}/contact",
        headers=headers,
        json={"full_name": "Appointment request", "phone": "+1 (555) 123-4567"},
    )
    assert contact.status_code == 201, contact.text
    intake = client.post(
        f"{thread_url}/crm-intake",
        headers=headers,
        json={"title": "Appointment request"},
    )
    assert intake.status_code == 200, intake.text
    detail = client.get(thread_url).json()
    assert detail["whatsapp_reply_mode"] == "test"
    assert detail["reply_unavailable"] is None
    sent: list[str] = []

    def send(address: str, **options: dict) -> httpx.Response:
        assert address == "https://graph.facebook.com/v21.0/123456/messages"
        assert options["json"]["type"] == "text"
        assert "template" not in options["json"]
        sent.append(options["json"]["to"])
        return httpx.Response(200, json={"messages": [{"id": "wamid.test-reply"}]})

    monkeypatch.setattr(whatsapp.httpx, "post", send)
    template = client.post(
        f"{thread_url}/submit-for-approval",
        headers=headers,
        json={
            "recipient": "15551234567",
            "body": "Template reply",
            "template_name": "hello_world",
        },
    )
    assert template.status_code == 409
    assert template.json()["error"]["code"] == "whatsapp_template_unavailable"
    assert sent == []
    approval = client.post(
        f"{thread_url}/submit-for-approval",
        headers=headers,
        json={"recipient": "15551234567", "body": "We received your appointment request."},
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["status"] == "pending"
    approval_id = uuid.UUID(approval.json()["approval_id"])
    assert client.post(
        f"/api/v1/organizations/{org.id}/approvals/{approval_id}/approve", headers=headers
    ).status_code == 200
    assert sent == []
    execute_approved(db, org.id, approval_id)
    assert sent == ["15551234567"]
    outbound = client.get(thread_url).json()["messages"][-1]
    assert outbound["direction"] == "outbound"
    assert outbound["delivery_status"] == "sent"
    settings = get_settings()
    assert settings.whatsapp_live_enabled is False
    assert settings.email_mode != "live"
    blocked = client.post(
        f"{thread_url}/submit-for-approval",
        headers=headers,
        json={"recipient": "15551234567", "body": "Second reply"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "whatsapp_reply_unavailable"
    monkeypatch.setattr(settings, "email_mode", "live")
    monkeypatch.setattr(settings, "whatsapp_live_enabled", True)
    with pytest.raises(AppError) as live_gate:
        whatsapp.send_whatsapp_text(
            db, org.id, "15551234567", "Should not send", test_reply=True
        )
    assert live_gate.value.code == "whatsapp_test_reply_unavailable"
    assert sent == ["15551234567"]
    monkeypatch.setattr(settings, "email_mode", "sandbox")
    monkeypatch.setattr(settings, "whatsapp_live_enabled", False)
    replaced = client.put(
        url,
        headers=headers,
        json={
            "provider": "meta",
            "config": {
                "business_account_id": "12345",
                "phone_number_id": "123456",
                "whatsapp_test_recipient": "19995550000",
            },
            "expected_version": version,
        },
    )
    assert replaced.status_code == 200, replaced.text
    db.expire_all()
    kept = db.scalar(select(IntegrationConfig).where(IntegrationConfig.id == record.id))
    assert kept is not None
    assert kept.config["whatsapp_test_recipient"] == "15551234567"
    assert kept.config["whatsapp_test_reply_message_id"] == "wamid.test-reply"


def test_rejected_test_reply_can_be_retried_until_one_send_succeeds(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = make_organization(db, "Retry reply", "whatsapp-test-retry")
    admin = make_user(db, "whatsapp-retry-admin@example.com")
    make_membership(db, admin, org, MembershipRole.admin)
    headers = _csrf(login(client, admin.email, PASSWORD))
    url = f"/api/v1/organizations/{org.id}/integration-configs/whatsapp"
    saved = client.put(
        url,
        headers=headers,
        json={
            "provider": "meta",
            "config": {"business_account_id": "12345", "phone_number_id": "123456"},
            "credentials": json.dumps({"access_token": "disposable-meta-token"}),
        },
    )
    monkeypatch.setattr(
        "app.api.v1.integrations.httpx.get",
        lambda *_args, **_kwargs: httpx.Response(200, json={"id": "123456"}),
    )
    assert client.post(f"{url}/verify", headers=headers).json()["verified"]
    secret = "disposable-retry-secret"
    monkeypatch.setattr(get_settings(), "whatsapp_webhook_app_secret", secret)
    body = json.dumps(
        {
            "entry": [
                {
                    "id": "12345",
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "123456"},
                                "messages": [
                                    {
                                        "type": "text",
                                        "id": "wamid.retry",
                                        "from": "15551234567",
                                        "text": {"body": "Hello"},
                                    }
                                ],
                            }
                        }
                    ],
                }
            ]
        }
    ).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert (
        client.post(
            f"/api/v1/organizations/{org.id}/inbox/webhooks/whatsapp",
            content=body,
            headers={"x-hub-signature-256": signature},
        ).json()["accepted"]
        == 1
    )
    _graph(monkeypatch, {"id": "123456", "verified_name": "Test Number", "account_mode": "SANDBOX"})
    approved = client.put(
        f"/api/v1/organizations/{org.id}/integration-configs/whatsapp/test-reply-recipient",
        headers=headers,
        json={"phone": "15551234567", "expected_version": saved.json()["credential_version"]},
    )
    assert approved.status_code == 200, approved.text
    conversation = db.scalar(
        select(InboxConversation).where(InboxConversation.organization_id == org.id)
    )
    assert conversation is not None
    contact = crm.create_contact(
        db,
        org.id,
        {"full_name": "Retry customer", "phone": "15551234567"},
    )
    conversation.contact_id = contact.id
    message = db.scalar(
        select(InboxMessage).where(InboxMessage.conversation_id == conversation.id)
    )
    assert message is not None
    message.created_at = datetime.now(UTC) - timedelta(hours=25)
    db.commit()
    mode, reason = whatsapp_test.whatsapp_reply_availability(db, conversation)
    assert mode is None
    assert reason is not None and "customer-service window" in reason
    message.created_at = datetime.now(UTC)
    db.commit()
    calls = {"count": 0}

    def send(*_args: object, **_kwargs: object) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(400, json={"error": {"code": 131030, "message": "not allowed"}})
        if calls["count"] == 2:
            return httpx.Response(400, json={"error": {"message": "rejected"}})
        return httpx.Response(200, json={"messages": [{"id": "wamid.retry-ok"}]})

    monkeypatch.setattr(whatsapp.httpx, "post", send)
    with pytest.raises(AppError) as not_allowed:
        whatsapp.send_whatsapp_text(db, org.id, "15551234567", "First attempt", test_reply=True)
    assert not_allowed.value.code == "whatsapp_recipient_not_allowed"
    with pytest.raises(AppError) as rejected:
        whatsapp.send_whatsapp_text(db, org.id, "15551234567", "Second attempt", test_reply=True)
    assert rejected.value.code == "whatsapp_provider_error"
    assert calls["count"] == 2
    assert (
        whatsapp.send_whatsapp_text(db, org.id, "15551234567", "Third attempt", test_reply=True)
        == "wamid.retry-ok"
    )
    with pytest.raises(AppError) as used:
        whatsapp.send_whatsapp_text(db, org.id, "15551234567", "Fourth attempt", test_reply=True)
    assert used.value.code == "whatsapp_test_reply_already_sent"
    assert calls["count"] == 3
