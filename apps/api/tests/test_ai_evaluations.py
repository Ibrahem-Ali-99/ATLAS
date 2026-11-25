import uuid
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.identity.models import MembershipRole
from app.domains.inbox.models import InboxConversation, InboxMessage
from app.integrations.language import get_chat_client, get_embedding_client
from tests.ai_clients import GroundedChatClient, HashEmbeddingClient
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf, _org


def _evaluation_client(client: TestClient) -> TestClient:
    application = cast(Any, client.app)
    application.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    application.dependency_overrides[get_chat_client] = lambda: GroundedChatClient()
    return client


def test_assistant_evaluation_is_non_sending_and_tenant_scoped(
    client: TestClient, db: Session
) -> None:
    user = make_user(db, "eval-owner@example.com")
    outsider = make_user(db, "eval-outsider@example.com")
    organization = make_organization(db, "Evaluation Org", "evaluation-org")
    other = make_organization(db, "Other Org", "other-evaluation-org")
    make_membership(db, user, organization, MembershipRole.admin)
    make_membership(db, outsider, other, MembershipRole.admin)
    api = _evaluation_client(client)
    session = login(api, "eval-owner@example.com", PASSWORD)
    headers = _csrf(session)
    org_id = _org(session)
    created = api.post(
        f"/api/v1/organizations/{org_id}/knowledge/evaluations/questions",
        json={
            "question": "What is the private policy?",
            "scenario": "missing_knowledge",
            "expected_behavior": "fallback",
            "expected_evidence": ["private policy"],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    run = api.post(
        f"/api/v1/organizations/{org_id}/knowledge/evaluations/questions/{created.json()['id']}/run",
        headers=headers,
    )
    assert run.status_code == 200, run.text
    assert run.json()["case_result"]["side_effects"] == "none"
    assert run.json()["answer_grounded"] is True

    api.cookies.clear()
    outsider_session = login(api, "eval-outsider@example.com", PASSWORD)
    stolen = api.get(
        f"/api/v1/organizations/{org_id}/knowledge/evaluations/runs",
        headers=_csrf(outsider_session),
    )
    assert stolen.status_code == 404


def test_inbox_evaluation_uses_persisted_conversation_without_writing_messages(
    client: TestClient, db: Session
) -> None:
    user = make_user(db, "inbox-eval@example.com")
    organization = make_organization(db, "Inbox Evaluation", "inbox-evaluation")
    make_membership(db, user, organization, MembershipRole.admin)
    conversation = InboxConversation(
        organization_id=organization.id,
        subject="Capacity question",
        channel="email",
    )
    db.add(conversation)
    db.flush()
    db.add(
        InboxMessage(
            organization_id=organization.id,
            conversation_id=conversation.id,
            sender="customer@example.com",
            recipient="support@example.com",
            body="Please connect me with a human about capacity.",
            direction="inbound",
            channel="email",
            provider_message_id=f"eval-{uuid.uuid4()}",
        )
    )
    db.commit()
    api = _evaluation_client(client)
    session = login(api, "inbox-eval@example.com", PASSWORD)
    headers = _csrf(session)
    org_id = _org(session)
    created = api.post(
        f"/api/v1/organizations/{org_id}/knowledge/evaluations/questions",
        json={
            "question": "Draft a reply",
            "scenario": "human_handoff",
            "expected_behavior": "handoff",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    before = db.query(InboxMessage).count()
    run = api.post(
        f"/api/v1/organizations/{org_id}/knowledge/evaluations/questions/{created.json()['id']}/run-inbox/{conversation.id}",
        headers=headers,
    )
    assert run.status_code == 200, run.text
    assert run.json()["case_result"]["side_effects"] == "none"
    assert db.query(InboxMessage).count() == before
