"""Inbox ownership, unread state, and archival that keeps the message history."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.inbox import _register_inbound
from app.domains.identity.models import MembershipRole
from app.domains.inbox.models import InboxConversation, InboxMessage, InboxStatus
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf, _org


def _thread(
    db: Session,
    organization_id: uuid.UUID,
    *,
    subject: str,
    channel: str = "email",
    assigned_to: uuid.UUID | None = None,
    inbound_at: datetime | None = None,
) -> InboxConversation:
    conversation = InboxConversation(
        organization_id=organization_id,
        subject=subject,
        channel=channel,
        status=InboxStatus.open,
        assigned_to=assigned_to,
        unread_count=1,
    )
    db.add(conversation)
    db.flush()
    db.add(
        InboxMessage(
            organization_id=organization_id,
            conversation_id=conversation.id,
            sender="customer@example.com",
            recipient="workspace@example.com",
            body="I need help with an appointment",
            direction="inbound",
            channel=channel,
            delivery_status="received",
            provider_message_id=f"provider-{uuid.uuid4()}",
            created_at=inbound_at or datetime.now(UTC),
        )
    )
    db.commit()
    db.refresh(conversation)
    return conversation


def test_archive_keeps_messages_and_a_new_customer_message_returns_the_thread(
    client: TestClient, db: Session
) -> None:
    owner = make_user(db, "inbox-owner@example.com", full_name="Inbox Owner")
    colleague = make_user(db, "inbox-colleague@example.com", full_name="Inbox Colleague")
    outsider = make_user(db, "inbox-outsider@example.com")
    organization = make_organization(db, "Inbox Workspace", f"inbox-{uuid.uuid4().hex[:8]}")
    other = make_organization(db, "Other Workspace", f"other-{uuid.uuid4().hex[:8]}")
    make_membership(db, owner, organization, MembershipRole.admin)
    make_membership(db, colleague, organization, MembershipRole.staff)
    make_membership(db, outsider, other, MembershipRole.admin)
    mine = _thread(db, organization.id, subject="Mine to follow up", assigned_to=owner.id)
    theirs = _thread(
        db, organization.id, subject="Colleague conversation", assigned_to=colleague.id
    )
    whatsapp = _thread(
        db,
        organization.id,
        subject="WhatsApp window",
        channel="whatsapp",
        inbound_at=datetime.now(UTC) - timedelta(hours=2),
    )

    session = login(client, "inbox-owner@example.com", PASSWORD)
    headers = _csrf(session)
    organization_id = _org(session)
    root = f"/api/v1/organizations/{organization_id}/inbox"

    listed = client.get(root)
    assert listed.status_code == 200, listed.text
    by_subject = {item["subject"]: item for item in listed.json()}
    assert by_subject["Mine to follow up"]["assignee_name"] == "Inbox Owner"
    assert by_subject["Colleague conversation"]["unread_count"] == 1

    mine_only = client.get(root, params={"assigned": "mine"})
    assert [item["subject"] for item in mine_only.json()] == ["Mine to follow up"]

    detail = client.get(f"{root}/{whatsapp.id}")
    assert detail.status_code == 200, detail.text
    window = detail.json()["whatsapp_service_window"]
    assert detail.json()["customer"]["email"] is None
    assert window["open"] is True
    assert window["provider"] == "unavailable"
    assert window["closes_at"] is not None

    archived = client.post(f"{root}/{mine.id}/archive", headers=headers)
    assert archived.status_code == 200, archived.text
    active = client.get(root)
    assert mine.subject not in {item["subject"] for item in active.json()}
    stored = client.get(f"{root}/{mine.id}")
    assert stored.status_code == 200
    assert len(stored.json()["messages"]) == 1
    assert stored.json()["archived_at"] is not None

    hidden = client.get(root, params={"retention": "archived"})
    assert [item["id"] for item in hidden.json()] == [str(mine.id)]

    client.cookies.clear()
    other_session = login(client, "inbox-outsider@example.com", PASSWORD)
    other_root = f"/api/v1/organizations/{_org(other_session)}/inbox"
    blocked = client.post(
        f"{other_root}/{mine.id}/restore", headers=_csrf(other_session)
    )
    assert blocked.status_code == 404
    client.cookies.clear()
    headers = _csrf(login(client, "inbox-owner@example.com", PASSWORD))

    restored = client.post(f"{root}/{mine.id}/restore", headers=headers)
    assert restored.status_code == 200
    assert any(item["id"] == str(mine.id) for item in client.get(root).json())

    read = client.patch(
        f"{root}/{theirs.id}/read",
        json={"updated_at": client.get(f"{root}/{theirs.id}").json()["updated_at"]},
        headers=headers,
    )
    assert read.status_code == 200 and read.json()["marked"] is True
    unread = client.patch(f"{root}/{theirs.id}/unread", headers=headers)
    assert unread.status_code == 200 and unread.json()["unread_count"] == 1
    unchanged = client.get(f"{root}/{theirs.id}").json()["updated_at"]
    again = client.patch(
        f"{root}/{theirs.id}/read",
        json={"updated_at": unchanged},
        headers=headers,
    )
    assert again.json()["marked"] is True

    client.post(f"{root}/{whatsapp.id}/archive", headers=headers)
    db.expire_all()
    row = db.get(InboxConversation, whatsapp.id)
    assert row is not None and row.archived_at is not None
    _register_inbound(row, "I am writing again")
    db.commit()
    returned = client.get(root, params={"channel": "whatsapp"})
    assert [item["id"] for item in returned.json()] == [str(whatsapp.id)]
    assert returned.json()[0]["unread_count"] == 2


def test_reply_approval_uses_the_channel_recipient_and_does_not_send(
    client: TestClient, db: Session
) -> None:
    owner = make_user(db, "reply-owner@example.com", full_name="Reply Owner")
    organization = make_organization(db, "Reply Workspace", f"reply-{uuid.uuid4().hex[:8]}")
    make_membership(db, owner, organization, MembershipRole.admin)
    session = login(client, owner.email, PASSWORD)
    headers = _csrf(session)
    root = f"/api/v1/organizations/{_org(session)}"
    conversation = _thread(db, organization.id, subject="Fictional quay note")
    body = {"recipient": "fictional@example.com", "subject": "Fictional quay note", "body": "We can review this internally."}

    missing_lead = client.post(f"{root}/inbox/{conversation.id}/submit-for-approval", json=body, headers=headers)
    assert missing_lead.status_code == 422
    assert missing_lead.json()["error"]["code"] == "approval_requires_lead"

    company = client.post(f"{root}/companies", json={"name": "Fictional Quay"}, headers=headers)
    assert company.status_code == 201, company.text
    contact = client.post(
        f"{root}/contacts",
        json={"full_name": "Fictional Recipient", "email": "fictional@example.com", "company_id": company.json()["id"]},
        headers=headers,
    )
    assert contact.status_code == 201, contact.text
    lead = client.post(
        f"{root}/leads",
        json={"title": "Fictional quay request", "company_id": company.json()["id"], "contact_id": contact.json()["id"]},
        headers=headers,
    )
    assert lead.status_code == 201, lead.text
    linked = client.patch(f"{root}/inbox/{conversation.id}/lead", json={"lead_id": lead.json()["id"]}, headers=headers)
    assert linked.status_code == 200, linked.text

    missing_inquiry = client.post(f"{root}/inbox/{conversation.id}/submit-for-approval", json=body, headers=headers)
    assert missing_inquiry.status_code == 422
    assert missing_inquiry.json()["error"]["code"] == "reply_inquiry_required"
    inquiry = client.post(
        f"{root}/inquiries",
        json={"subject": "Fictional quay note", "body": "Please review the quay note.", "lead_id": lead.json()["id"]},
        headers=headers,
    )
    assert inquiry.status_code == 201, inquiry.text

    mismatched = client.post(
        f"{root}/inbox/{conversation.id}/submit-for-approval",
        json={**body, "recipient": "other@example.com"},
        headers=headers,
    )
    assert mismatched.status_code == 422
    assert mismatched.json()["error"]["code"] == "recipient_not_owned"

    detail = client.get(f"{root}/inbox/{conversation.id}")
    assert detail.json()["reply_recipient"] == "fictional@example.com"
    created = client.post(
        f"{root}/inbox/{conversation.id}/submit-for-approval",
        json={**body, "recipient": detail.json()["reply_recipient"]},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    assert created.json()["status"] == "pending"
    approval = client.get(f"{root}/approvals/{created.json()['approval_id']}")
    assert approval.status_code == 200
    assert approval.json()["status"] == "pending"
    assert approval.json()["action_type"] == "prepare_customer_response"
    assert "sent" not in approval.json()["status"]
