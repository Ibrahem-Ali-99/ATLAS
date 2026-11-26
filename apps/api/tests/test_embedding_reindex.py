import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.identity.models import MembershipRole
from app.domains.integrations.models import IntegrationConfig
from app.domains.knowledge import reindex
from app.domains.knowledge.models import Chunk, Document, DocumentStatus
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf


def test_candidate_failure_then_promotion_preserves_document_and_chunk(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = make_organization(db, "Reindex workspace", "reindex-workspace")
    staff = make_user(db, "reindex-staff@example.com")
    admin = make_user(db, "reindex-admin@example.com")
    make_membership(db, staff, org, MembershipRole.staff)
    make_membership(db, admin, org, MembershipRole.admin)
    doc = Document(
        organization_id=org.id,
        uploaded_by=admin.id,
        title="Return terms",
        filename="terms.txt",
        media_type="text/plain",
        byte_size=12,
        storage_path=str(uuid.uuid4()),
        status=DocumentStatus.ready,
    )
    db.add(doc)
    db.flush()
    settings = get_settings()
    chunk = Chunk(
        organization_id=org.id,
        document_id=doc.id,
        chunk_index=0,
        content="Returns within 14 days",
        embedding=[1.0] * 1536,
        embedding_model=settings.embedding_model,
    )
    db.add(chunk)
    db.commit()
    path = f"/api/v1/organizations/{org.id}/knowledge/embedding-reindex"
    headers = _csrf(login(client, staff.email, PASSWORD))
    assert client.get(path).status_code == 403
    assert client.post(path, headers=headers, json={}).status_code == 403
    headers = _csrf(login(client, admin.email, PASSWORD))
    target = {
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "replacement",
        "dimensions": 768,
        "credentials": "fixture-target-key",
    }
    assert client.post(path, headers=headers, json=target).status_code == 202

    def unavailable(*args, **kwargs):
        raise AppError(502, "embedding_unavailable", "Test failure")

    monkeypatch.setattr(reindex.OpenAICompatibleEmbeddingClient, "embed", unavailable)
    assert reindex.run_batch(db)
    assert client.get(path).json()["status"] == "failed"
    assert db.scalar(select(IntegrationConfig.id)) is None
    db.refresh(chunk)
    assert chunk.embedding is not None and chunk.embedding_768 is None
    assert client.post(path, headers=headers, json=target).status_code == 202
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(path).json()["status"] == "cancelled"
    assert client.post(path, headers=headers, json=target).status_code == 202
    monkeypatch.setattr(
        reindex.OpenAICompatibleEmbeddingClient,
        "embed",
        lambda _self, texts: [[1.0] * 768 for _ in texts],
    )
    assert reindex.run_batch(db)
    assert client.get(path).json()["staged_chunks"] == 1
    db.refresh(chunk)
    assert chunk.embedding_768 is None
    assert reindex.run_batch(db)
    assert client.get(path).json()["status"] == "completed"
    db.refresh(chunk)
    db.refresh(doc)
    assert chunk.embedding is None and chunk.embedding_768 is not None
    assert chunk.embedding_model == "replacement" and chunk.document_id == doc.id
    assert doc.status == DocumentStatus.ready and chunk.content == "Returns within 14 days"
    record = db.scalars(select(IntegrationConfig)).one()
    assert record.config["dimensions"] == 768
    assert record.encrypted_credentials != "fixture-target-key"


def test_loopback_ollama_accepts_only_local_http() -> None:
    assert reindex._loopback_ollama("http://127.0.0.1:11434/v1")
    assert reindex._loopback_ollama("http://localhost:11434/v1/")
    assert reindex._loopback_ollama("http://[::1]:11434/v1")
    assert not reindex._loopback_ollama("https://127.0.0.1:11434/v1")
    assert not reindex._loopback_ollama("http://user:pass@127.0.0.1:11434/v1")
    assert not reindex._loopback_ollama("http://127.0.0.1:11434/v1?model=1")
    assert not reindex._loopback_ollama("http://127.0.0.1:11434/embeddings")
    assert not reindex._loopback_ollama("http://ollama:11434/v1")
    assert not reindex._loopback_ollama("http://10.0.0.8:11434/v1")


def test_remote_embedding_host_is_rejected(client: TestClient, db: Session) -> None:
    org = make_organization(db, "Remote embedding workspace", "remote-embedding")
    admin = make_user(db, "remote-embedding@example.com")
    make_membership(db, admin, org, MembershipRole.admin)
    db.commit()
    settings = get_settings()
    remote = "http://example.com/v1"
    if settings.embedding_base_url.rstrip("/") == remote:
        remote = "http://embeddings.example/v1"
    headers = _csrf(login(client, admin.email, PASSWORD))
    path = f"/api/v1/organizations/{org.id}/knowledge/embedding-reindex"
    for base_url in (remote, "https://127.0.0.1:11434/v1", "http://127.0.0.1:11434/v1?x=1"):
        response = client.post(
            path,
            headers=headers,
            json={
                "provider": "ollama",
                "base_url": base_url,
                "model": "nomic-embed-text:v1.5",
                "dimensions": 768,
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "reindex_provider_invalid"
    assert client.get(path).json() is None


def test_local_ollama_rebuild_fails_cancels_and_promotes_disposable_document(
    client: TestClient, db: Session
) -> None:
    import httpx

    try:
        probe = httpx.post(
            "http://127.0.0.1:11434/v1/embeddings",
            json={"model": "nomic-embed-text:v1.5", "input": ["ATLAS embedding verification"]},
            timeout=20,
        )
    except httpx.HTTPError:
        pytest.skip("local Ollama is not available")
    if probe.status_code != 200:
        pytest.skip("local Ollama is not available")

    org = make_organization(db, "Local embedding workspace", "local-embedding")
    other = make_organization(db, "Untouched embedding workspace", "untouched-embedding")
    admin = make_user(db, "local-embedding@example.com")
    make_membership(db, admin, org, MembershipRole.admin)
    original = "Disposable passage for the local embedding rebuild"
    chunk = _ready_chunk(db, org.id, admin.id, original)
    untouched = _ready_chunk(db, other.id, admin.id, "Leave this passage on its current index")
    db.commit()
    headers = _csrf(login(client, admin.email, PASSWORD))
    path = f"/api/v1/organizations/{org.id}/knowledge/embedding-reindex"
    local = {
        "provider": "ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "nomic-embed-text:v1.5",
        "dimensions": 768,
    }
    missing = {**local, "model": "atlas-missing-model"}
    assert client.post(path, headers=headers, json=missing).status_code == 202
    assert reindex.run_batch(db)
    failed = client.get(path).json()
    assert failed["status"] == "failed"
    assert failed["error_code"]
    db.refresh(chunk)
    assert chunk.embedding is not None and chunk.embedding_768 is None
    assert chunk.content == original

    assert client.post(path, headers=headers, json=local).status_code == 202
    assert reindex.run_batch(db)
    staged = client.get(path).json()
    assert staged["status"] == "building" and staged["staged_chunks"] == 1
    db.refresh(chunk)
    assert chunk.embedding_768 is None and chunk.content == original
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(path).json()["status"] == "cancelled"
    db.refresh(chunk)
    assert chunk.embedding is not None and chunk.embedding_768 is None

    assert client.post(path, headers=headers, json=local).status_code == 202
    assert reindex.run_batch(db)
    assert reindex.run_batch(db)
    completed = client.get(path).json()
    assert completed["status"] == "completed" and completed["error_code"] is None
    db.refresh(chunk)
    db.refresh(untouched)
    document = db.get(Document, chunk.document_id)
    assert document is not None and document.status == DocumentStatus.ready
    assert (
        chunk.embedding is None
        and list(chunk.embedding_768)
        and len(list(chunk.embedding_768)) == 768
    )
    assert chunk.embedding_model == "nomic-embed-text:v1.5"
    assert chunk.content == original
    assert untouched.embedding is not None and untouched.embedding_768 is None
    record = db.scalars(
        select(IntegrationConfig).where(IntegrationConfig.organization_id == org.id)
    ).one()
    assert record.provider == "ollama"
    assert record.config["base_url"] == "http://127.0.0.1:11434/v1"
    assert record.config["dimensions"] == 768
    assert record.encrypted_credentials is None
    assert (
        db.scalar(select(IntegrationConfig.id).where(IntegrationConfig.organization_id == other.id))
        is None
    )


def _ready_chunk(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, content: str
) -> Chunk:
    document = Document(
        organization_id=organization_id,
        uploaded_by=actor_id,
        title="Disposable note",
        filename="note.txt",
        media_type="text/plain",
        byte_size=len(content.encode()),
        storage_path=str(uuid.uuid4()),
        status=DocumentStatus.ready,
    )
    db.add(document)
    db.flush()
    chunk = Chunk(
        organization_id=organization_id,
        document_id=document.id,
        chunk_index=0,
        content=content,
        embedding=[1.0] * 1536,
        embedding_model=get_settings().embedding_model,
    )
    db.add(chunk)
    db.flush()
    return chunk
