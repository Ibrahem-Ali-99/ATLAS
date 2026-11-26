import hashlib
import hmac
import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1 import integrations
from app.core.config import get_settings
from app.domains.approvals.service import execute_approved
from app.domains.crm.service import create_inquiry, create_lead
from app.domains.identity.models import MembershipRole
from app.domains.inbox.models import InboxConversation, InboxMessage
from app.integrations import whatsapp
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf


def test_whatsapp_connection_threads_messages_and_stops_on_disconnect(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = make_organization(db, "Messaging", "messaging-workspace")
    other = make_organization(db, "Other messaging", "other-messaging-workspace")
    admin = make_user(db, "message-admin@example.com")
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
    assert saved.status_code == 200, saved.text
    assert saved.json()["verified_at"] is None
    assert "disposable-meta-token" not in saved.text
    monkeypatch.setattr(
        integrations.httpx,
        "get",
        lambda *_args, **_kwargs: httpx.Response(401, json={"error": {"error_subcode": 463}}),
    )
    expired = client.post(f"{url}/verify", headers=headers)
    assert expired.json()["detail"] == "WhatsApp access token expired"
    assert not expired.json()["verified"]
    monkeypatch.setattr(
        integrations.httpx,
        "get",
        lambda *_args, **_kwargs: httpx.Response(200, json={"id": "123456"}),
    )
    assert client.post(f"{url}/verify", headers=headers).json()["verified"]
    secret = "disposable-callback-signing-secret"
    monkeypatch.setattr(get_settings(), "whatsapp_webhook_app_secret", secret)

    def incoming(message_id: str, organization=org):
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
                                            "id": message_id,
                                            "from": "15551234567",
                                            "text": {"body": "Customer update"},
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
        return client.post(
            f"/api/v1/organizations/{organization.id}/inbox/webhooks/whatsapp",
            content=body,
            headers={"x-hub-signature-256": signed},
        )

    assert incoming("message-1", other).json()["accepted"] == 0
    assert incoming("message-1").json()["accepted"] == 1
    assert incoming("message-2").json()["accepted"] == 1
    assert incoming("message-2").json()["duplicates"] == 1
    threads = db.scalars(
        select(InboxConversation).where(InboxConversation.organization_id == org.id)
    ).all()
    assert len(threads) == 1
    assert threads[0].unread_count == 2
    assert (
        len(
            db.scalars(
                select(InboxMessage).where(InboxMessage.conversation_id == threads[0].id)
            ).all()
        )
        == 2
    )
    conversation_id = threads[0].id
    root = f"/api/v1/organizations/{org.id}"
    thread_url = f"{root}/inbox/{conversation_id}"
    assert "replies are disabled" in client.get(thread_url).json()["reply_unavailable"]
    contact = client.post(
        f"{thread_url}/contact",
        headers=headers,
        json={"full_name": "WhatsApp contact", "phone": "+1 (555) 123-4567"},
    )
    assert contact.status_code == 201, contact.text
    lead = create_lead(
        db,
        org.id,
        admin.id,
        {
            "title": "Customer update",
            "status": "new",
            "contact_id": uuid.UUID(contact.json()["contact_id"]),
        },
    )
    create_inquiry(
        db, org.id, {"subject": "Customer update", "body": "Check status", "lead_id": lead.id}
    )
    assert (
        client.patch(
            f"{thread_url}/lead", headers=headers, json={"lead_id": str(lead.id)}
        ).status_code
        == 200
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "email_mode", "live")
    monkeypatch.setattr(settings, "whatsapp_live_enabled", True)
    assert client.get(thread_url).json()["reply_unavailable"] is None
    sent = []

    def send(address: str, **options: dict) -> httpx.Response:
        assert address == "https://graph.facebook.com/v21.0/123456/messages"
        assert options["json"]["to"] == "15551234567"
        sent.append(options["json"]["text"]["body"])
        return httpx.Response(200, json={"messages": [{"id": "wamid.acceptance"}]})

    monkeypatch.setattr(whatsapp.httpx, "post", send)
    approval = client.post(
        f"{thread_url}/submit-for-approval",
        headers=headers,
        json={"recipient": "15551234567", "body": "Your CRM request is ready for review."},
    )
    assert approval.status_code == 200, approval.text
    approval_id = uuid.UUID(approval.json()["approval_id"])
    assert not sent
    assert (
        client.post(f"{root}/approvals/{approval_id}/approve", headers=headers).status_code == 200
    )
    execute_approved(db, org.id, approval_id)
    assert sent == ["Your CRM request is ready for review."]
    assert client.get(thread_url).json()["messages"][-1]["delivery_status"] == "sent"
    disconnected = client.post(
        f"{url}/disable",
        headers=headers,
        json={"expected_version": saved.json()["credential_version"]},
    )
    assert disconnected.status_code == 200
    assert client.post(f"{url}/verify", headers=headers).status_code == 409
    assert incoming("message-3").json()["accepted"] == 0
