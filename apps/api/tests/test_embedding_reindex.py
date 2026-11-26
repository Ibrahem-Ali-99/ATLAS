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
