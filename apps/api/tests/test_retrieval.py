import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.identity.models import MembershipRole
from app.domains.knowledge import retrieval
from app.domains.knowledge.models import Chunk, Document, DocumentStatus
from app.domains.knowledge.service import (
    claim_ingestion_job,
    resume_incomplete_documents,
    run_ingestion_job,
)
from app.integrations.language import get_embedding_client
from tests.ai_clients import HashEmbeddingClient
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf, _org


class _BrokenEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise AppError(
            502, "embedding_failed", "The embedding provider returned an unexpected response"
        )


def _process_one(embedder: object | None = None) -> bool:
    worker_id = f"test-worker-{uuid.uuid4()}"
    job = claim_ingestion_job(worker_id)
    if job is None:
        return False
    run_ingestion_job(job, worker_id, embedder)  # type: ignore[arg-type]
    return True


@pytest.fixture
def embedded_client(client: TestClient) -> TestClient:
    client.app.dependency_overrides[get_embedding_client] = lambda: HashEmbeddingClient()
    return client


def test_vector_distance_threshold_drops_far_neighbors_while_text_matches_remain() -> None:
    chunk = SimpleNamespace(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_index=0,
        page_number=2,
        content="alpha",
    )
    fused: dict[uuid.UUID, retrieval.RetrievedChunk] = {}
    retrieval._fuse_vector(fused, [(chunk, "Doc", 0.4)], 0.2)
    assert fused == {}
    retrieval._fuse_vector(fused, [(chunk, "Doc", 0.2)], 0.2)
    assert chunk.id in fused
    other = SimpleNamespace(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_index=1,
        page_number=None,
        content="beta",
    )
    lexical: dict[uuid.UUID, retrieval.RetrievedChunk] = {}
    retrieval._fuse_text(lexical, [(other, "Other", 0.01)])
    assert other.id in lexical


def test_retrieval_positive_negative_ambiguous_and_recovery(
    embedded_client: TestClient, db: Session
) -> None:
    user = make_user(db, "ada@example.com")
    outsider = make_user(db, "outsider@example.org")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    other = make_organization(db, "Northwind", "northwind")
    make_membership(db, user, atlas, MembershipRole.admin)
    make_membership(db, outsider, other, MembershipRole.admin)
    ada = login(embedded_client, "ada@example.com", PASSWORD)
    headers = _csrf(ada)
    org = _org(ada)

    def upload(name: str, text: str) -> str:
        response = embedded_client.post(
            f"/api/v1/organizations/{org}/documents",
            files={"file": (name, text.encode(), "text/plain")},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        return str(response.json()["id"])

    harbor_id = upload(
        "harbor-services.txt",
        "Harbor warehousing includes cold storage and bonded yards.",
    )
    office_id = upload(
        "office-storage.txt",
        "The office storage closet holds paper and spare chairs.",
    )
    upload("cafeteria-menu.txt", "The cafeteria menu lists soup and bread.")
    assert _process_one(HashEmbeddingClient())
    assert _process_one(HashEmbeddingClient())
    assert _process_one(HashEmbeddingClient())

    def titles(query: str) -> list[str]:
        found = embedded_client.get(
            f"/api/v1/organizations/{org}/documents/search", params={"q": query}
        )
        assert found.status_code == 200, found.text
        return [item["document_title"] for item in found.json()["items"]]

    positive = titles("cold storage warehousing")
    assert positive[0] == "harbor-services"
    assert "cafeteria-menu" not in positive
    assert titles("zzzzqqqq unknown glacier policy") == []
    ambiguous = set(titles("storage"))
    assert ambiguous == {"harbor-services", "office-storage"}

    chunks = embedded_client.get(f"/api/v1/organizations/{org}/documents/{harbor_id}/chunks")
    assert len(chunks.json()["items"]) == 1
    reindexed = embedded_client.post(
        f"/api/v1/organizations/{org}/documents/{harbor_id}/reindex", headers=headers
    )
    assert reindexed.status_code == 200, reindexed.text
    chunks = embedded_client.get(f"/api/v1/organizations/{org}/documents/{harbor_id}/chunks")
    assert len(chunks.json()["items"]) == 1

    document = db.get(Document, uuid.UUID(harbor_id))
    assert document is not None
    document.status = DocumentStatus.processing
    db.commit()
    assert resume_incomplete_documents(HashEmbeddingClient()) == 1
    assert _process_one(HashEmbeddingClient())
    db.expire_all()
    resumed = db.get(Document, uuid.UUID(harbor_id))
    assert resumed is not None
    assert resumed.status == DocumentStatus.ready
    chunks = embedded_client.get(f"/api/v1/organizations/{org}/documents/{harbor_id}/chunks")
    assert len(chunks.json()["items"]) == 1
    assert resume_incomplete_documents(HashEmbeddingClient()) == 0

    db.execute(delete(Chunk).where(Chunk.document_id == resumed.id))
    resumed.status = DocumentStatus.pending
    resumed.error_message = None
    db.commit()
    assert resume_incomplete_documents(HashEmbeddingClient()) == 1
    assert _process_one(HashEmbeddingClient())
    chunks = embedded_client.get(f"/api/v1/organizations/{org}/documents/{harbor_id}/chunks")
    assert len(chunks.json()["items"]) == 1

    office = db.get(Document, uuid.UUID(office_id))
    assert office is not None
    office.status = DocumentStatus.pending
    office.error_message = None
    db.commit()
    assert resume_incomplete_documents(HashEmbeddingClient()) == 1
    office_worker = f"test-worker-{uuid.uuid4()}"
    office_job = claim_ingestion_job(office_worker)
    assert office_job is not None
    run_ingestion_job(office_job, office_worker, _BrokenEmbedder())
    db.expire_all()
    office = db.get(Document, uuid.UUID(office_id))
    assert office is not None
    assert office.status == DocumentStatus.ready
    assert office.error_message == "The embedding provider returned an unexpected response"
    office_chunks = embedded_client.get(f"/api/v1/organizations/{org}/documents/{office_id}/chunks")
    assert len(office_chunks.json()["items"]) == 1

    embedded_client.cookies.clear()
    other_session = login(embedded_client, "outsider@example.org", PASSWORD)
    hidden = embedded_client.get(
        f"/api/v1/organizations/{_org(other_session)}/documents/search",
        params={"q": "cold storage"},
    )
    assert hidden.status_code == 200
    assert hidden.json()["items"] == []
