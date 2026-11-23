import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.integrations.models import IntegrationType
from app.domains.integrations.schemas import IntegrationInput
from app.domains.integrations.service import create_configuration, disable_configuration
from app.domains.knowledge.models import DocumentStatus
from app.domains.knowledge.service import ingest_document, store_upload
from app.integrations.language import OpenAICompatibleChatClient
from app.integrations.mcp_runtime import mcp_process_env
from app.integrations.resolver import resolve_settings
from tests.factories import make_organization, make_user


def test_concurrent_organizations_resolve_distinct_chat_clients(db: Session) -> None:
    atlas = make_organization(db, "Atlas", "phase2b-atlas")
    northwind = make_organization(db, "Northwind", "phase2b-northwind")
    create_configuration(
        db,
        atlas.id,
        IntegrationInput(
            integration_type="chat",
            provider="groq",
            config={"base_url": "https://groq.example/v1", "model": "model-a"},
        ),
        "credential-a",
    )
    create_configuration(
        db,
        northwind.id,
        IntegrationInput(
            integration_type="chat",
            provider="openai",
            config={"base_url": "https://openai.example/v1", "model": "model-b"},
        ),
        "credential-b",
    )
    db.commit()

    def resolve(org_id: uuid.UUID) -> tuple[str, str, str]:
        from app.core.database import SessionLocal

        session = SessionLocal()
        try:
            settings = resolve_settings(session, org_id, "chat")
            client = OpenAICompatibleChatClient(settings)
            return (
                client._settings.llm_provider,
                client._settings.llm_model,
                client._settings.llm_api_key,
            )
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(resolve, [atlas.id, northwind.id]))
    assert results == [("groq", "model-a", "credential-a"), ("openai", "model-b", "credential-b")]


def test_missing_disabled_and_invalid_overrides_fail_closed(db: Session) -> None:
    missing = make_organization(db, "Missing", "phase2b-missing")
    base = get_settings()
    assert resolve_settings(db, missing.id, "chat") == base
    disabled = make_organization(db, "Disabled", "phase2b-disabled")
    record = create_configuration(
        db, disabled.id, IntegrationInput(integration_type="chat", provider="groq"), "secret"
    )
    db.commit()
    disable_configuration(
        db, disabled.id, IntegrationType.chat, expected_version=record.credential_version
    )
    db.commit()
    with pytest.raises(AppError, match="disabled"):
        resolve_settings(db, disabled.id, "chat")
    broken = make_organization(db, "Broken", "phase2b-broken")
    broken_record = create_configuration(
        db, broken.id, IntegrationInput(integration_type="chat", provider="groq"), "secret"
    )
    broken_record.encrypted_credentials = "enc:v1:not-valid"
    db.commit()
    with pytest.raises(AppError) as error:
        resolve_settings(db, broken.id, "chat")
    assert error.value.code == "integration_secret_invalid"


def test_embedding_override_preserves_model_width_and_mcp_excludes_chat_key(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization = make_organization(db, "Embedding", "phase2b-embedding")
    create_configuration(
        db,
        organization.id,
        IntegrationInput(
            integration_type="embedding",
            provider="ollama",
            config={
                "base_url": "http://ollama:11434/v1",
                "model": "nomic-embed-text:v1.5",
                "dimensions": 768,
            },
        ),
    )
    db.commit()
    settings = resolve_settings(db, organization.id, "embedding")
    assert (
        settings.embedding_provider,
        settings.embedding_model,
        settings.embedding_dimensions,
    ) == (
        "ollama",
        "nomic-embed-text:v1.5",
        768,
    )
    for key in (
        "ATLAS_EMBEDDING_PROVIDER",
        "ATLAS_EMBEDDING_BASE_URL",
        "ATLAS_EMBEDDING_MODEL",
        "ATLAS_EMBEDDING_DIMENSIONS",
        "ATLAS_EMBEDDING_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("app.integrations.mcp_runtime.SessionLocal", lambda: db)
    env = mcp_process_env(organization_id=str(organization.id))
    assert env["ATLAS_EMBEDDING_MODEL"] == "nomic-embed-text:v1.5"
    assert env["ATLAS_EMBEDDING_DIMENSIONS"] == "768"
    assert "ATLAS_LLM_API_KEY" not in env


def test_background_ingestion_fails_closed_for_disabled_originating_org(db: Session) -> None:
    organization = make_organization(db, "Indexer", "phase2b-indexer")
    user = make_user(db, "phase2b-indexer@example.org")
    record = create_configuration(
        db, organization.id, IntegrationInput(integration_type="embedding", provider="ollama")
    )
    db.commit()
    disable_configuration(
        db,
        organization.id,
        IntegrationType.embedding,
        expected_version=record.credential_version,
    )
    db.commit()
    document = store_upload(
        db,
        organization.id,
        user.id,
        filename="policy.txt",
        media_type="text/plain",
        payload=b"This document must not be indexed while the provider is disabled.",
    )
    ingest_document(document.id)
    db.refresh(document)
    assert document.status == DocumentStatus.failed
    assert document.error_message

