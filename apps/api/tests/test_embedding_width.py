import uuid

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.identity.models import MembershipRole
from app.domains.knowledge.models import Chunk, Document, DocumentStatus
from app.domains.knowledge.retrieval import search_chunks
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login


class _Width:
    def __init__(self, vector: list[float]) -> None:
        self.vector = vector

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.vector for _ in texts]


def test_search_does_not_compare_a_different_model_or_width(db: Session, monkeypatch) -> None:
    user = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-width")
    make_membership(db, user, atlas, MembershipRole.admin)
    current = [0.0] * 768
    current[0] = 1.0
    other = [0.0] * 768
    other[0] = 1.0
    document = Document(
        organization_id=atlas.id,
        uploaded_by=user.id,
        title="Pier notes",
        filename="pier.txt",
        media_type="text/plain",
        byte_size=20,
        storage_path="tests/pier.txt",
        status=DocumentStatus.ready,
    )
    db.add(document)
    db.flush()
    db.add(
        Chunk(
            organization_id=atlas.id,
            document_id=document.id,
            chunk_index=0,
            content="alpha passage",
            embedding_768=current,
            embedding_model="nomic-embed-text",
        )
    )
    db.add(
        Chunk(
            organization_id=atlas.id,
            document_id=document.id,
            chunk_index=1,
            content="beta passage",
            embedding_768=other,
            embedding_model="other-model",
        )
    )
    db.add(
        Chunk(
            organization_id=atlas.id,
            document_id=document.id,
            chunk_index=2,
            content="gamma passage",
            embedding=[0.0] * 1536,
            embedding_model=None,
        )
    )
    db.commit()
    settings = get_settings().model_copy(
        update={
            "embedding_provider": "ollama",
            "embedding_model": "nomic-embed-text",
            "embedding_dimensions": 768,
        }
    )
    monkeypatch.setattr("app.domains.knowledge.retrieval.get_settings", lambda: settings)
    hits = search_chunks(db, atlas.id, "qqqqqq", _Width(current))
    assert [hit.content for hit in hits] == ["alpha passage"]


def test_provider_status_counts_only_the_member_organization(
    client: TestClient, db: Session, monkeypatch
) -> None:
    user = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-status")
    other = make_organization(db, "Northwind", "northwind-status")
    make_membership(db, user, atlas, MembershipRole.admin)
    _ready_legacy(db, atlas.id, user.id)
    _ready_legacy(db, other.id, user.id)
    db.commit()
    settings = get_settings().model_copy(
        update={
            "embedding_provider": "ollama",
            "embedding_model": "nomic-embed-text",
            "embedding_dimensions": 768,
            "llm_provider": "groq",
            "llm_model": "openai/gpt-oss-20b",
            "llm_api_key": "",
        }
    )
    monkeypatch.setattr("app.integrations.provider_status.get_settings", lambda: settings)
    monkeypatch.setattr("app.domains.knowledge.vectors.get_settings", lambda: settings)

    def offline(*_args: object, **_kwargs: object) -> None:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("app.integrations.provider_status.httpx.get", offline)
    ada = login(client, "ada@example.com", PASSWORD)
    response = client.get(f"/api/v1/organizations/{atlas.id}/provider-status")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["llm_provider"] == "groq"
    assert body["llm_ready"] is False
    assert body["embedding_provider"] == "ollama"
    assert body["embedding_ready"] is False
    assert "Ollama" in body["embedding_detail"]
    assert body["incompatible_documents"] == 1
    assert "gsk" not in response.text
    assert "api_key" not in response.text
    outsider = client.get(f"/api/v1/organizations/{other.id}/provider-status")
    assert outsider.status_code == 404
    assert ada["user"]


def _ready_legacy(db: Session, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
    document = Document(
        organization_id=organization_id,
        uploaded_by=user_id,
        title="Legacy",
        filename="legacy.txt",
        media_type="text/plain",
        byte_size=6,
        storage_path="tests/legacy.txt",
        status=DocumentStatus.ready,
    )
    db.add(document)
    db.flush()
    db.add(
        Chunk(
            organization_id=organization_id,
            document_id=document.id,
            chunk_index=0,
            content="legacy",
            embedding=[0.0] * 1536,
        )
    )
