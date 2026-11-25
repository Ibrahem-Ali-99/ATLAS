import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.assistant.service import conversation_title
from app.domains.identity.models import MembershipRole
from app.domains.knowledge.service import claim_ingestion_job, run_ingestion_job
from app.integrations.language import get_chat_client, get_embedding_client
from tests.ai_clients import GroundedChatClient, HashEmbeddingClient
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf, _org


@pytest.fixture
def grounded_client(client: TestClient) -> TestClient:
    client.app.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    client.app.dependency_overrides[get_chat_client] = lambda: GroundedChatClient()
    return client


def _process_ingestion() -> None:
    worker_id = f"assistant-test-worker-{uuid.uuid4()}"
    job = claim_ingestion_job(worker_id)
    assert job is not None
    run_ingestion_job(job, worker_id, HashEmbeddingClient())


def test_assistant_cites_documents_and_crm_and_refuses_other_organizations(
    grounded_client: TestClient, db: Session
) -> None:
    admin = make_user(db, "ada@example.com")
    outsider = make_user(db, "outsider@example.org")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    northwind = make_organization(db, "Northwind", "northwind")
    make_membership(db, admin, atlas, MembershipRole.admin)
    make_membership(db, outsider, northwind, MembershipRole.admin)
    ada = login(grounded_client, "ada@example.com", PASSWORD)
    headers = _csrf(ada)
    org = _org(ada)

    company = grounded_client.post(
        f"/api/v1/organizations/{org}/companies",
        json={"name": "Harbor & Co.", "industry": "Logistics"},
        headers=headers,
    )
    assert company.status_code == 201, company.text
    lead = grounded_client.post(
        f"/api/v1/organizations/{org}/leads",
        json={
            "title": "North pier expansion",
            "status": "qualified",
            "company_id": company.json()["id"],
            "notes": "Synthetic lead for warehousing capacity.",
        },
        headers=headers,
    )
    assert lead.status_code == 201, lead.text
    uploaded = grounded_client.post(
        f"/api/v1/organizations/{org}/documents",
        files={
            "file": (
                "harbor-services.txt",
                b"Harbor warehousing includes cold storage and bonded yards.",
                "text/plain",
            )
        },
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["status"] == "pending" or uploaded.json()["status"] == "ready"
    _process_ingestion()
    document = grounded_client.get(f"/api/v1/organizations/{org}/documents/{uploaded.json()['id']}")
    assert document.json()["status"] == "ready"

    created = grounded_client.post(
        f"/api/v1/organizations/{org}/conversations",
        json={"title": "Harbor"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]
    services = grounded_client.post(
        f"/api/v1/organizations/{org}/conversations/{conversation_id}/messages",
        json={"content": "What cold storage warehousing services does Harbor offer?"},
        headers=headers,
    )
    assert services.status_code == 200, services.text
    assert services.json()["message"]["content"] == (
        "Grounded answer from the supplied company records."
    )
    assert services.json()["message"]["sources"] == []

    pipeline = grounded_client.post(
        f"/api/v1/organizations/{org}/conversations/{conversation_id}/messages",
        json={"content": "What is the status of the North pier expansion?"},
        headers=headers,
    )
    assert pipeline.status_code == 200, pipeline.text
    assert pipeline.json()["message"]["sources"] == []

    missing = grounded_client.post(
        f"/api/v1/organizations/{org}/conversations/{conversation_id}/messages",
        json={"content": "zzzzqqqq unknown glacier policy"},
        headers=headers,
    )
    assert missing.status_code == 200, missing.text
    assert missing.json()["message"]["sources"] == []
    assert "could not find" in missing.json()["message"]["content"].lower()

    history = grounded_client.get(f"/api/v1/organizations/{org}/conversations/{conversation_id}")
    assert history.status_code == 200
    assert len(history.json()["messages"]) >= 6

    streamed = grounded_client.post(
        f"/api/v1/organizations/{org}/conversations/{conversation_id}/messages/stream",
        json={"content": "What cold storage warehousing services does Harbor offer?"},
        headers=headers,
    )
    assert streamed.status_code == 200, streamed.text
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert "event: done" in streamed.text
    assert "Grounded answer from the supplied company records." in streamed.text

    grounded_client.cookies.clear()
    other = login(grounded_client, "outsider@example.org", PASSWORD)
    stolen = grounded_client.get(
        f"/api/v1/organizations/{_org(other)}/conversations/{conversation_id}"
    )
    assert stolen.status_code == 404


def test_assistant_reports_missing_model_credentials(client: TestClient, db: Session) -> None:
    user = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, user, atlas, MembershipRole.admin)
    ada = login(client, "ada@example.com", PASSWORD)
    headers = _csrf(ada)
    org = _org(ada)
    created = client.post(
        f"/api/v1/organizations/{org}/conversations",
        json={},
        headers=headers,
    )
    lead = client.post(
        f"/api/v1/organizations/{org}/leads",
        json={"title": "North pier expansion", "status": "new"},
        headers=headers,
    )
    assert lead.status_code == 201
    response = client.post(
        f"/api/v1/organizations/{org}/conversations/{created.json()['id']}/messages",
        json={"content": "What is the status of the North pier expansion?"},
        headers=headers,
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] in {"llm_unconfigured", "embedding_unconfigured"}
    history = client.get(f"/api/v1/organizations/{org}/conversations/{created.json()['id']}")
    assert history.status_code == 200
    assert any("not configured" in item["content"].lower() for item in history.json()["messages"])


def test_assistant_stores_a_malformed_embedding_failure(client: TestClient, db: Session) -> None:
    class BrokenEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            raise AppError(
                502, "embedding_failed", "The embedding provider returned an unexpected response"
            )

    client.app.dependency_overrides[get_embedding_client] = lambda: BrokenEmbedder()
    user = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, user, atlas, MembershipRole.admin)
    ada = login(client, "ada@example.com", PASSWORD)
    headers = _csrf(ada)
    org = _org(ada)
    created = client.post(f"/api/v1/organizations/{org}/conversations", json={}, headers=headers)
    response = client.post(
        f"/api/v1/organizations/{org}/conversations/{created.json()['id']}/messages",
        json={"content": "zzzzqqqq unknown glacier policy"},
        headers=headers,
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "embedding_failed"
    history = client.get(f"/api/v1/organizations/{org}/conversations/{created.json()['id']}")
    assert history.status_code == 200
    assert history.json()["messages"][-1]["sources"] == []
    assert "unexpected response" in history.json()["messages"][-1]["content"]


def test_conversation_title_uses_the_question_and_stops_on_a_word() -> None:
    assert conversation_title("   ") == "Untitled conversation"
    assert conversation_title("How large is the bonded yard?") == "How large is the bonded yard?"
    title = conversation_title(("bonded yard capacity " * 8).strip())
    assert len(title) <= 72
    assert title.startswith("bonded yard capacity")
    assert " " in title


def test_untitled_conversation_is_renamed_from_the_first_question(
    grounded_client: TestClient, db: Session
) -> None:
    user = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, user, atlas, MembershipRole.admin)
    ada = login(grounded_client, "ada@example.com", PASSWORD)
    headers = _csrf(ada)
    org = _org(ada)
    created = grounded_client.post(
        f"/api/v1/organizations/{org}/conversations", json={}, headers=headers
    )
    assert created.status_code == 201
    assert created.json()["title"] == "New conversation"
    question = "How large is the bonded yard?"
    sent = grounded_client.post(
        f"/api/v1/organizations/{org}/conversations/{created.json()['id']}/messages",
        json={"content": question},
        headers=headers,
    )
    assert sent.status_code == 200, sent.text
    conversation_id = created.json()["id"]
    history = grounded_client.get(f"/api/v1/organizations/{org}/conversations/{conversation_id}")
    assert history.json()["title"] == question
