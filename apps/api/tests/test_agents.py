import os
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.agents.workflow import TOOL_RETRY, graph_node_names, retry_tool_error
from app.domains.crm.models import Lead
from app.domains.crm.service import create_company, create_contact, create_inquiry
from app.domains.identity.models import MembershipRole
from app.domains.knowledge.models import Chunk, Document, DocumentStatus
from app.integrations.business_mcp import TransientToolError
from app.integrations.language import OpenAICompatibleChatClient, get_chat_client
from tests.ai_clients import ClassificationDouble, hash_embedding
from tests.embedding_stub import EmbeddingStub
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login

PASSAGE = "Harbor warehousing includes cold storage and bonded yards."


def test_graph_has_no_approval_tool_and_retries_are_bounded() -> None:
    assert "approve" not in graph_node_names()
    assert graph_node_names() == {
        "load_inquiry",
        "classify",
        "retrieve_knowledge",
        "lookup_customer",
        "qualify",
        "propose",
        "await_approval",
        "execute",
        "record_outcome",
    }
    assert TOOL_RETRY.max_attempts == 3
    assert retry_tool_error(TransientToolError("unavailable"))
    assert not retry_tool_error(AppError(503, "llm_unconfigured", "missing"))


def test_missing_model_credentials_fail_the_run(client: TestClient, db: Session) -> None:
    """The real chat client rejects an empty key. This does not call a live model."""

    org, headers = _member(client, db)
    inquiry = create_inquiry(db, uuid.UUID(org), {"subject": "Rates", "body": PASSAGE})
    empty = get_settings().model_copy(update={"llm_api_key": ""})
    client.app.dependency_overrides[get_chat_client] = lambda: OpenAICompatibleChatClient(empty)
    try:
        response = client.post(
            f"/api/v1/organizations/{org}/agent-runs",
            json={"inquiry_id": str(inquiry.id)},
            headers=headers,
        )
    finally:
        client.app.dependency_overrides.pop(get_chat_client, None)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_unconfigured"
    listed = client.get(f"/api/v1/organizations/{org}/agent-runs")
    assert listed.status_code == 200
    run = listed.json()["items"][0]
    assert run["status"] == "failed"
    assert run["error_code"] == "llm_unconfigured"
    assert _lead_count(db, uuid.UUID(org)) == 0
    from app.domains.observability.models import OperationTrace

    trace = db.scalar(
        select(OperationTrace).where(OperationTrace.agent_run_id == uuid.UUID(str(run["id"])))
    )
    assert trace is not None
    assert trace.status == "failed"
    assert trace.error_code == "llm_unconfigured"
    assert trace.langfuse_status == "unconfigured"


def test_successful_run_pauses_resumes_and_writes_once(client: TestClient, db: Session) -> None:
    """Classification and embeddings come from test doubles, not a live provider."""

    org, headers = _member(client, db)
    organization_id = uuid.UUID(org)
    _knowledge(db, organization_id)
    inquiry = create_inquiry(
        db,
        organization_id,
        {"subject": "Bonded storage", "body": f"Mina Patel asked: {PASSAGE}"},
    )
    client.app.dependency_overrides[get_chat_client] = lambda: ClassificationDouble()
    try:
        with _EmbeddingEnv():
            started = client.post(
                f"/api/v1/organizations/{org}/agent-runs",
                json={"inquiry_id": str(inquiry.id)},
                headers=headers,
            )
            assert started.status_code == 201, started.text
            body = started.json()
            assert body["run"]["status"] == "awaiting_approval"
            assert body["run"]["qualification"] == "qualified"
            assert _steps(body, "classify") == ["warehousing"]
            titles = [
                hit["document_title"]
                for event in body["events"]
                if event["step"] == "retrieve_knowledge"
                for hit in event["detail"]["hits"]
            ]
            assert "Harbor services" in titles
            assert _lead_count(db, organization_id) == 0
            run_id = body["run"]["id"]
            for approval in body["approvals"]:
                decision = client.post(
                    f"/api/v1/organizations/{org}/approvals/{approval['id']}/approve",
                    json={},
                    headers=headers,
                )
                assert decision.status_code == 200, decision.text
            early = client.post(
                f"/api/v1/organizations/{org}/agent-runs/{run_id}/resume",
                headers=headers,
            )
            assert early.status_code == 200, early.text
            finished = early.json()
            assert finished["run"]["status"] == "completed"
            assert _steps(finished, "classify") == ["warehousing"]
            outcome = finished["events"][-1]["detail"]["outcome"]
            assert isinstance(outcome, str) and outcome.startswith("3 executed")
    finally:
        client.app.dependency_overrides.pop(get_chat_client, None)

    leads = client.get(f"/api/v1/organizations/{org}/leads")
    assert leads.status_code == 200
    assert leads.json()["total"] == 1
    lead = leads.json()["items"][0]
    assert lead["title"] == "Bonded storage inquiry"
    assert lead["status"] == "qualified"
    interactions = client.get(f"/api/v1/organizations/{org}/leads/{lead['id']}/interactions")
    kinds = {item["kind"] for item in interactions.json()}
    assert kinds == {"email", "call"}
    again = client.post(
        f"/api/v1/organizations/{org}/agent-runs/{run_id}/resume",
        headers=headers,
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "invalid_transition"
    assert client.get(f"/api/v1/organizations/{org}/leads").json()["total"] == 1


def test_rejected_run_writes_nothing(client: TestClient, db: Session) -> None:
    org, headers = _member(client, db)
    organization_id = uuid.UUID(org)
    inquiry = create_inquiry(db, organization_id, {"subject": "Rates", "body": PASSAGE})
    client.app.dependency_overrides[get_chat_client] = lambda: ClassificationDouble()
    try:
        with _EmbeddingEnv():
            started = client.post(
                f"/api/v1/organizations/{org}/agent-runs",
                json={"inquiry_id": str(inquiry.id)},
                headers=headers,
            )
            assert started.status_code == 201, started.text
            body = started.json()
            run_id = body["run"]["id"]
            for approval in body["approvals"]:
                rejected = client.post(
                    f"/api/v1/organizations/{org}/approvals/{approval['id']}/reject",
                    json={"note": "Not now"},
                    headers=headers,
                )
                assert rejected.status_code == 200, rejected.text
            resumed = client.post(
                f"/api/v1/organizations/{org}/agent-runs/{run_id}/resume",
                headers=headers,
            )
            assert resumed.status_code == 200, resumed.text
            assert resumed.json()["run"]["status"] == "completed"
            assert resumed.json()["events"][-1]["detail"]["outcome"].startswith("0 executed")
    finally:
        client.app.dependency_overrides.pop(get_chat_client, None)
    assert _lead_count(db, organization_id) == 0
    again = client.post(
        f"/api/v1/organizations/{org}/agent-runs/{run_id}/resume",
        headers=headers,
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "invalid_transition"


def test_other_organization_cannot_start_a_run(client: TestClient, db: Session) -> None:
    admin = make_user(db, "ada@example.com")
    outsider = make_user(db, "outsider@example.org")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    northwind = make_organization(db, "Northwind", "northwind")
    make_membership(db, admin, atlas, MembershipRole.admin)
    make_membership(db, outsider, northwind, MembershipRole.admin)
    inquiry = create_inquiry(db, atlas.id, {"subject": "Rates", "body": "Storage"})
    other = login(client, "outsider@example.org", PASSWORD)
    response = client.post(
        f"/api/v1/organizations/{atlas.id}/agent-runs",
        json={"inquiry_id": str(inquiry.id)},
        headers={"X-CSRF-Token": str(other["csrf_token"])},
    )
    assert response.status_code == 404


def _member(client: TestClient, db: Session) -> tuple[str, dict[str, str]]:
    admin = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, admin, atlas, MembershipRole.admin)
    company = create_company(db, atlas.id, {"name": "Harbor"})
    create_contact(
        db,
        atlas.id,
        {"full_name": "Mina Patel", "email": "mina@harbor.example", "company_id": company.id},
    )
    ada = login(client, "ada@example.com", PASSWORD)
    memberships = ada["memberships"]
    assert isinstance(memberships, list)
    first = memberships[0]
    assert isinstance(first, dict)
    return str(first["organization_id"]), {"X-CSRF-Token": str(ada["csrf_token"])}


def _knowledge(db: Session, organization_id: uuid.UUID) -> None:
    from app.domains.identity.models import Membership

    user_id = db.scalar(
        select(Membership.user_id).where(Membership.organization_id == organization_id)
    )
    assert user_id is not None
    document = Document(
        organization_id=organization_id,
        uploaded_by=user_id,
        title="Harbor services",
        filename="harbor.txt",
        media_type="text/plain",
        byte_size=len(PASSAGE),
        storage_path="tests/harbor.txt",
        status=DocumentStatus.ready,
    )
    db.add(document)
    db.flush()
    chunk = Chunk(
        organization_id=organization_id,
        document_id=document.id,
        chunk_index=0,
        content=PASSAGE,
        embedding=hash_embedding(PASSAGE),
    )
    db.add(chunk)
    db.flush()
    db.execute(
        update(Chunk)
        .where(Chunk.id == chunk.id)
        .values(search_vector=func.to_tsvector("english", Chunk.content))
    )
    db.commit()


class _EmbeddingEnv:
    def __enter__(self) -> None:
        self._stub = EmbeddingStub()
        self._stub.__enter__()
        keys = ("ATLAS_EMBEDDING_API_KEY", "ATLAS_EMBEDDING_BASE_URL")
        self._previous = {key: os.environ.get(key) for key in keys}
        os.environ["ATLAS_EMBEDDING_API_KEY"] = "test-double"
        os.environ["ATLAS_EMBEDDING_BASE_URL"] = self._stub.url

    def __exit__(self, *_exc: object) -> None:
        for key, value in self._previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._stub.__exit__(*_exc)


def _steps(body: dict[str, object], step: str) -> list[object]:
    events = body["events"]
    assert isinstance(events, list)
    found: list[object] = []
    for event in events:
        assert isinstance(event, dict)
        if event["step"] == step:
            detail = event["detail"]
            assert isinstance(detail, dict)
            found.append(detail.get("category"))
    return found


def _lead_count(db: Session, organization_id: uuid.UUID) -> int:
    db.rollback()
    total = db.scalar(
        select(func.count()).select_from(Lead).where(Lead.organization_id == organization_id)
    )
    return int(total or 0)
