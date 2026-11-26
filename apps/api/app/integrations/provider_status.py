"""Read-only provider readiness. This never returns a key or a prompt."""

import uuid

import httpx
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domains.demo.access import organization_is_visitor
from app.domains.knowledge.vectors import incompatible_document_count
from app.integrations.resolver import resolve_settings


class ProviderStatus(BaseModel):
    llm_provider: str
    llm_model: str
    llm_ready: bool
    llm_detail: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    embedding_ready: bool
    embedding_detail: str
    incompatible_documents: int


def provider_status(db: Session, organization_id: uuid.UUID) -> ProviderStatus:
    if organization_is_visitor(db, organization_id):
        return ProviderStatus(
            llm_provider="double",
            llm_model="demonstration",
            llm_ready=True,
            llm_detail=(
                "Demonstration mode. Answers stay in this session and do not call a paid model."
            ),
            embedding_provider="double",
            embedding_model="demonstration",
            embedding_dimensions=0,
            embedding_ready=True,
            embedding_detail=(
                "Demonstration mode. Document search stays in this session "
                "and does not call a paid model."
            ),
            incompatible_documents=0,
        )
    base_settings = get_settings()
    settings = resolve_settings(db, organization_id, "chat", base_settings=base_settings)
    embedding_settings = resolve_settings(
        db, organization_id, "embedding", base_settings=base_settings
    )
    llm_ready, llm_detail = _llm_status(settings)
    embedding_ready, embedding_detail = _embedding_status(embedding_settings)
    return ProviderStatus(
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        llm_ready=llm_ready,
        llm_detail=llm_detail,
        embedding_provider=embedding_settings.embedding_provider,
        embedding_model=embedding_settings.embedding_model,
        embedding_dimensions=embedding_settings.embedding_dimensions,
        embedding_ready=embedding_ready,
        embedding_detail=embedding_detail,
        incompatible_documents=incompatible_document_count(db, organization_id, embedding_settings),
    )


def _llm_status(settings: Settings) -> tuple[bool, str]:
    if settings.llm_provider == "double":
        return True, "Deterministic answers are enabled. They are not a live model."
    if not settings.llm_api_key.strip():
        return False, "The language model key is empty."
    if settings.llm_provider == "groq":
        return True, "Groq is configured for chat."
    return True, "The OpenAI-compatible chat provider is configured."


def _embedding_status(settings: Settings) -> tuple[bool, str]:
    if settings.embedding_provider == "double":
        return True, "Deterministic embeddings are enabled. They are not a live model."
    if settings.embedding_provider == "ollama":
        return _ollama_status(settings)
    if not settings.embedding_api_key.strip():
        return False, "The embedding key is empty."
    return True, "The OpenAI-compatible embedding provider is configured."


def _ollama_status(settings: Settings) -> tuple[bool, str]:
    root = settings.embedding_base_url.rstrip("/").removesuffix("/v1")
    try:
        response = httpx.get(f"{root}/api/tags", timeout=2)
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return False, "Ollama is not running at the configured address."
    if response.status_code >= 400 or not isinstance(payload, dict):
        return False, "Ollama is not running at the configured address."
    models = payload.get("models")
    rows = models if isinstance(models, list) else []
    names = [item.get("name", "") for item in rows if isinstance(item, dict)]
    model = settings.embedding_model
    installed = any(name == model or name.startswith(f"{model}:") for name in names)
    if not installed:
        return False, "Ollama is running, and the configured embedding model is not installed."
    return True, "Ollama is running and the configured model is installed."
