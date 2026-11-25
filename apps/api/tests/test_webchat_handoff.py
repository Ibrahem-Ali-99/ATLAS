import uuid
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.identity.models import MembershipRole
from app.domains.inbox.models import InboxConversation, InboxMessage
from app.integrations.language import get_chat_client, get_embedding_client
from tests.ai_clients import GroundedChatClient, HashEmbeddingClient
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf, _org


def _api(client: TestClient) -> TestClient:
    application = cast(Any, client.app)
    application.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    application.dependency_overrides[get_chat_client] = lambda: GroundedChatClient()
    return client


def _widget(api: TestClient, email: str, db: Session, mode: str) -> tuple[str, str, dict[str, str]]:
    user = make_user(db, email)
    org = make_organization(db, f"{email} org", f"org-{uuid.uuid4().hex[:10]}")
    make_membership(db, user, org, MembershipRole.admin)
    session = login(api, email, PASSWORD)
    headers = _csrf(session)
    organization_id = _org(session)
    saved = api.put(
        f"/api/v1/organizations/{organization_id}/inbox/widget",
        json={"allowed_domains": [], "operating_mode": mode},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    started = api.post(f"/api/v1/widget/{saved.json()['public_id']}/sessions")
    assert started.status_code == 200, started.text
    return organization_id, saved.json()["public_id"], started.json()


def test_handoff_takeover_staff_delivery_and_duplicate_protection(
    client: TestClient, db: Session
) -> None:
    api = _api(client)
    org_id, public_id, session = _widget(api, "webchat-admin@example.com", db, "ai_auto_reply")
    token = session["session_token"]
    conversation_id = session["conversation_id"]
    sent = api.post(
        f"/api/v1/widget/{public_id}/sessions/{token}/messages",
        json={"message": "Please connect me with a human", "client_message_id": "visitor-1"},
    )
    assert sent.status_code == 200
    api.cookies.clear()
    admin = login(api, "webchat-admin@example.com", PASSWORD)
    headers = _csrf(admin)
    takeover = api.post(
        f"/api/v1/organizations/{org_id}/inbox/{conversation_id}/takeover", headers=headers
    )
    assert takeover.status_code == 200, takeover.text
    staff = api.post(
        f"/api/v1/organizations/{org_id}/inbox/{conversation_id}/staff-message",
        json={"body": "A team member is here to help.", "client_message_id": "staff-1"},
        headers=headers,
    )
    assert staff.status_code == 200, staff.text
    duplicate = api.post(
        f"/api/v1/organizations/{org_id}/inbox/{conversation_id}/staff-message",
        json={"body": "A team member is here to help.", "client_message_id": "staff-1"},
        headers=headers,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"
    polled = api.get(f"/api/v1/widget/{public_id}/sessions/{token}/messages")
    assert polled.status_code == 200
    assert sum(item["body"] == "A team member is here to help." for item in polled.json()) == 1
    row = db.scalar(select(InboxConversation).where(InboxConversation.id == conversation_id))
    assert row is not None and row.assigned_to is not None and row.ai_resumed is False


def test_human_only_widget_does_not_auto_reply_and_sessions_are_isolated(
    client: TestClient, db: Session
) -> None:
    api = _api(client)
    org_id, public_id, session = _widget(api, "human-only@example.com", db, "human_review")
    message_count = db.scalar(select(func.count()).select_from(InboxMessage)) or 0
    sent = api.post(
        f"/api/v1/widget/{public_id}/sessions/{session['session_token']}/messages",
        json={"message": "Hello", "client_message_id": "visitor-human-only"},
    )
    assert sent.status_code == 200
    assert (db.scalar(select(func.count()).select_from(InboxMessage)) or 0) == message_count + 1
    stolen = api.get(
        f"/api/v1/widget/{public_id}/sessions/{uuid.uuid4()}/messages"
    )
    assert stolen.status_code == 401
    api.cookies.clear()
    staff = login(api, "human-only@example.com", PASSWORD)
    resume = api.post(
        f"/api/v1/organizations/{org_id}/inbox/{session['conversation_id']}/resume-ai",
        headers=_csrf(staff),
    )
    assert resume.status_code == 409
