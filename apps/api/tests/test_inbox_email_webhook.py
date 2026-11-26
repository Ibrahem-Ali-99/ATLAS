import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.crm.service import create_contact
from app.domains.identity.models import MembershipRole
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf


def test_email_gateway_binds_signature_to_workspace_and_threads_by_mailbox(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = make_organization(db, "Inbox gateway", "inbox-gateway")
    other = make_organization(db, "Other inbox gateway", "other-inbox-gateway")
    admin = make_user(db, "inbox-gateway@example.com")
    make_membership(db, admin, org, MembershipRole.admin)
    headers = _csrf(login(client, admin.email, PASSWORD))
    contact = create_contact(db, org.id, {"full_name": "Customer", "email": "Customer@example.com"})
    secret = "disposable-inbound-signing-key"
    monkeypatch.setattr(get_settings(), "inbox_webhook_secret", secret)
    path = f"/api/v1/organizations/{org.id}/inbox"

    def deliver(message_id: str, subject: str, mailbox: str, *, foreign: bool = False, age=0):
        body = json.dumps(
            {
                "message_id": message_id,
                "subject": subject,
                "body": "Customer request",
                "sender": "customer@example.com",
                "recipient": mailbox,
            }
        ).encode()
        timestamp = str(int(datetime.now(UTC).timestamp()) - age)
        signature = hmac.new(
            secret.encode(), f"v1.{org.id}.{timestamp}.".encode() + body, hashlib.sha256
        ).hexdigest()
        callback = path.replace(str(org.id), str(other.id)) if foreign else path
        return client.post(
            f"{callback}/webhooks/inbound",
            content=body,
            headers={"X-Atlas-Inbox-Signature": signature, "X-Atlas-Inbox-Timestamp": timestamp},
        )

    assert deliver("email-1", "Order", "support@example.com", foreign=True).status_code == 400
    assert deliver("email-1", "Order", "support@example.com", age=7200).status_code == 400
    first = deliver("email-1", "Order", "support@example.com").json()
    assert first["matched_contact"]
    assert deliver("email-1", "Order", "support@example.com").json()["status"] == "duplicate"
    assert (
        deliver("email-2", "Re: Order", "support@example.com").json()["conversation_id"]
        == (first["conversation_id"])
    )
    assert (
        deliver("email-3", "Order", "sales@example.com").json()["conversation_id"]
        != (first["conversation_id"])
    )
    thread = client.get(f"{path}/{first['conversation_id']}").json()
    assert thread["contact_id"] == str(contact.id)
    assert thread["unread_count"] == 2
    assert len(thread["messages"]) == 2
    intake = f"{path}/{first['conversation_id']}/crm-intake"
    captured = client.post(intake, headers=headers, json={"title": "First order"})
    assert captured.status_code == 200, captured.text
    records = captured.json()
    assert client.post(intake, headers=headers, json={"title": "Retry"}).json() == records
    root = path.removesuffix("/inbox")
    lead = client.get(f"{root}/leads/{records['lead_id']}").json()
    inquiry = client.get(f"{root}/inquiries/{records['inquiry_id']}").json()
    assert lead["contact_id"] == str(contact.id) and lead["title"] == "First order"
    assert inquiry["lead_id"] == lead["id"] and inquiry["body"] == "Customer request"
