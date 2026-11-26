"""Assistant proposals stay unsent until a person confirms, and then still wait for approval."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.approvals.models import Approval, ApprovalStatus
from app.domains.automation.models import CalendarBooking, EmailMessage, WorkflowTask
from app.domains.crm.models import Contact, Inquiry, Lead, LeadStatus
from app.domains.identity.models import MembershipRole
from app.integrations.language import get_chat_client, get_embedding_client
from tests.ai_clients import HashEmbeddingClient
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_assistant_routing import ForbiddenChat
from tests.test_crm import _csrf, _org


def _records(db: Session, organization_id: uuid.UUID, owner_id: uuid.UUID, title: str) -> Lead:
    contact = Contact(
        organization_id=organization_id,
        full_name=title,
        email=f"{title.split()[0].lower()}@example.com",
    )
    db.add(contact)
    db.flush()
    lead = Lead(
        organization_id=organization_id,
        contact_id=contact.id,
        owner_user_id=owner_id,
        title=title,
        status=LeadStatus.new,
        notes="Stored note for the shelf request.",
    )
    db.add(lead)
    db.flush()
    db.add(
        Inquiry(
            organization_id=organization_id,
            lead_id=lead.id,
            subject="Shelf request",
            body="Please quote the stored shelf.",
        )
    )
    db.commit()
    return lead


def test_summary_proposals_archive_and_no_external_send(client: TestClient, db: Session) -> None:
    owner = make_user(db, "assistant-owner@example.com", full_name="Assistant Owner")
    outsider = make_user(db, "assistant-outsider@example.com")
    organization = make_organization(db, "Assistant Workspace", f"assistant-{uuid.uuid4().hex[:8]}")
    other = make_organization(db, "Other Workspace", f"other-{uuid.uuid4().hex[:8]}")
    make_membership(db, owner, organization, MembershipRole.admin)
    make_membership(db, outsider, other, MembershipRole.admin)
    lead = _records(db, organization.id, owner.id, "Harbor Desk")
    _records(db, other.id, outsider.id, "Other Harbor")
    client.app.dependency_overrides[get_chat_client] = lambda: ForbiddenChat()
    client.app.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()

    session = login(client, "assistant-owner@example.com", PASSWORD)
    headers = _csrf(session)
    root = f"/api/v1/organizations/{_org(session)}"
    created = client.post(f"{root}/conversations", json={}, headers=headers)
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]
    thread = f"{root}/conversations/{conversation_id}"

    summary = client.post(
        f"{thread}/messages",
        json={"content": "Summarize the lead Harbor Desk"},
        headers=headers,
    )
    assert summary.status_code == 200, summary.text
    body = summary.json()["message"]["content"]
    assert "Harbor Desk" in body
    assert "Other Harbor" not in body
    assert "Stored note for the shelf request." in body
    assert "Please quote the stored shelf." in body
    assert "new" in body
    assert summary.json()["message"]["proposals"] == []

    denied = client.post(
        f"{thread}/messages",
        json={"content": "Please delete the Harbor Desk lead"},
        headers=headers,
    )
    assert denied.status_code == 200, denied.text
    assert "read-only" in denied.json()["message"]["content"].lower()
    assert db.scalar(select(func.count()).select_from(WorkflowTask)) == 0

    task = client.post(
        f"{thread}/messages",
        json={"content": "Create a follow-up task for Harbor Desk"},
        headers=headers,
    )
    assert task.status_code == 200, task.text
    proposal = task.json()["message"]["proposals"][0]
    assert proposal["kind"] == "task"
    assert proposal["result_label"].startswith("Proposed")
    submitted = client.post(
        f"{thread}/proposals/{proposal['id']}/submit", json={}, headers=headers
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["task_id"]
    assert "Task created" in submitted.json()["result_label"]
    stored_task = db.get(WorkflowTask, uuid.UUID(submitted.json()["task_id"]))
    assert stored_task is not None and stored_task.lead_id == lead.id
    again = client.post(f"{thread}/proposals/{proposal['id']}/submit", json={}, headers=headers)
    assert again.status_code == 409

    follow_up = client.post(
        f"{thread}/messages",
        json={"content": "Draft a follow-up for Harbor Desk"},
        headers=headers,
    )
    assert follow_up.status_code == 200, follow_up.text
    draft = follow_up.json()["message"]["proposals"][0]
    assert "harbor@example.com" in follow_up.json()["message"]["content"]
    text = follow_up.json()["message"]["content"].lower()
    assert "does not send" in draft["summary"].lower() or "does not send" in text
    requested = client.post(f"{thread}/proposals/{draft['id']}/submit", json={}, headers=headers)
    assert requested.status_code == 200, requested.text
    approval = db.get(Approval, uuid.UUID(requested.json()["approval_id"]))
    assert approval is not None and approval.status == ApprovalStatus.pending
    assert db.scalar(select(func.count()).select_from(EmailMessage)) == 0

    appointment = client.post(
        f"{thread}/messages",
        json={"content": "Request an appointment for Harbor Desk"},
        headers=headers,
    )
    assert appointment.status_code == 200, appointment.text
    booking = appointment.json()["message"]["proposals"][0]
    missing_time = client.post(
        f"{thread}/proposals/{booking['id']}/submit", json={}, headers=headers
    )
    assert missing_time.status_code == 422
    start = datetime.now(UTC) + timedelta(days=2)
    booked = client.post(
        f"{thread}/proposals/{booking['id']}/submit",
        json={"starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=1)).isoformat()},
        headers=headers,
    )
    assert booked.status_code == 200, booked.text
    assert booked.json()["approval_status"] == "pending"
    assert "Waiting for approval" in booked.json()["result_label"]
    assert db.scalar(select(func.count()).select_from(CalendarBooking)) == 0

    renamed = client.patch(thread, json={"title": "Harbor follow-up"}, headers=headers)
    assert renamed.status_code == 200 and renamed.json()["title"] == "Harbor follow-up"
    archived = client.post(f"{thread}/archive", headers=headers)
    assert archived.status_code == 200 and archived.json()["archived_at"]
    listed = client.get(f"{root}/conversations")
    assert conversation_id not in {item["id"] for item in listed.json()}
    hidden = client.get(f"{root}/conversations", params={"retention": "archived", "q": "Harbor"})
    assert [item["id"] for item in hidden.json()] == [conversation_id]
    detail = client.get(thread)
    assert detail.status_code == 200 and len(detail.json()["messages"]) >= 4

    client.cookies.clear()
    other_session = login(client, "assistant-outsider@example.com", PASSWORD)
    other_root = f"/api/v1/organizations/{_org(other_session)}/conversations/{conversation_id}"
    blocked = client.post(f"{other_root}/restore", headers=_csrf(other_session))
    assert blocked.status_code == 404
