import json
from collections.abc import Iterator
from typing import Any, Protocol

import httpx
import structlog

from app.core.config import Settings, get_settings
from app.core.errors import AppError

logger = structlog.get_logger(__name__)


class EmbeddingClient(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ChatClient(Protocol):
    def ensure_configured(self) -> None: ...

    def complete(self, system: str, user: str) -> str: ...

    def stream(self, system: str, user: str) -> Iterator[str]: ...


class OpenAICompatibleEmbeddingClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self._settings.embedding_api_key.strip():
            raise AppError(
                503,
                "embedding_unconfigured",
                "The embedding provider is not configured. Set ATLAS_EMBEDDING_API_KEY.",
            )
        response = httpx.post(
            f"{self._settings.embedding_base_url.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {self._settings.embedding_api_key}"},
            json={
                "model": self._settings.embedding_model,
                "input": texts,
                "dimensions": self._settings.embedding_dimensions,
            },
            timeout=60,
        )
        if response.status_code >= 400:
            raise AppError(502, "embedding_failed", "The embedding provider rejected the request")
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise AppError(
                502, "embedding_failed", "The embedding provider returned an unexpected response"
            ) from exc
        vectors = _embedding_vectors(payload, len(texts), self._settings.embedding_dimensions)
        _log_usage("embedding_usage", payload)
        return vectors


class OpenAICompatibleChatClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def ensure_configured(self) -> None:
        if not self._settings.llm_api_key.strip():
            raise AppError(
                503,
                "llm_unconfigured",
                "The language model is not configured. Set ATLAS_LLM_API_KEY.",
            )

    def complete(self, system: str, user: str) -> str:
        chunks = list(self.stream(system, user))
        return "".join(chunks).strip()

    def stream(self, system: str, user: str) -> Iterator[str]:
        self.ensure_configured()
        with httpx.stream(
            "POST",
            f"{self._settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self._settings.llm_api_key}"},
            json={
                "model": self._settings.llm_model,
                "stream": True,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=120,
        ) as response:
            if response.status_code >= 400:
                raise AppError(502, "llm_failed", "The language model rejected the request")
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    raise AppError(
                        502, "llm_failed", "The language model returned an unexpected response"
                    )
                _log_usage("llm_usage", payload)
                if isinstance(payload.get("error"), dict):
                    raise AppError(
                        502, "llm_failed", "The language model returned an unexpected response"
                    )
                choices = payload.get("choices") or []
                if not isinstance(choices, list) or not choices:
                    continue
                choice = choices[0] if isinstance(choices[0], dict) else {}
                delta_raw = choice.get("delta")
                delta = delta_raw if isinstance(delta_raw, dict) else {}
                text = delta.get("content")
                if isinstance(text, str) and text:
                    yield text


def _embedding_vectors(payload: object, count: int, dimensions: int) -> list[list[float]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise AppError(
            502, "embedding_failed", "The embedding provider returned an unexpected response"
        )
    rows = payload["data"]
    if any(not isinstance(row, dict) for row in rows):
        raise AppError(
            502, "embedding_failed", "The embedding provider returned an unexpected response"
        )
    ordered = sorted(rows, key=lambda item: item.get("index", 0))
    vectors: list[list[float]] = []
    for row in ordered:
        vector = row.get("embedding")
        if not isinstance(vector, list) or len(vector) != dimensions:
            raise AppError(
                502, "embedding_failed", "The embedding provider returned an unexpected response"
            )
        if any(type(value) not in {int, float} for value in vector):
            raise AppError(
                502, "embedding_failed", "The embedding provider returned an unexpected response"
            )
        vectors.append([float(value) for value in vector])
    if len(vectors) != count:
        raise AppError(
            502, "embedding_failed", "The embedding provider returned an unexpected response"
        )
    return vectors


def _log_usage(event: str, payload: dict[str, Any]) -> None:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    logger.info(event, prompt_tokens=prompt, completion_tokens=completion)
    from app.domains.observability.tracing import record_operation

    settings = get_settings()
    record_operation(
        operation=event,
        status="succeeded",
        provider="openai-compatible",
        model_name=settings.llm_model if event == "llm_usage" else settings.embedding_model,
        tokens_in=prompt if isinstance(prompt, int) else None,
        tokens_out=completion if isinstance(completion, int) else None,
    )


def get_embedding_client() -> EmbeddingClient:
    settings = get_settings()
    if settings.public_demo and settings.embedding_provider != "double":
        raise AppError(
            503,
            "embedding_unconfigured",
            "Paid model calls are disabled for this deployment.",
        )
    if settings.embedding_provider == "double":
        from app.integrations.doubles import DeterministicEmbeddingClient

        return DeterministicEmbeddingClient()
    return OpenAICompatibleEmbeddingClient(settings)


def get_chat_client() -> ChatClient:
    settings = get_settings()
    if settings.public_demo and settings.llm_provider != "double":
        raise AppError(
            503,
            "llm_unconfigured",
            "Paid model calls are disabled for this deployment.",
        )
    if settings.llm_provider == "double":
        from app.integrations.doubles import DeterministicChatClient

        return DeterministicChatClient()
    return OpenAICompatibleChatClient(settings)
