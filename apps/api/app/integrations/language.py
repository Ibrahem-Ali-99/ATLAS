import json
from collections.abc import Iterator
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError


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
        payload = response.json()
        rows = sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
        vectors = [row.get("embedding") for row in rows]
        if len(vectors) != len(texts) or any(not isinstance(vector, list) for vector in vectors):
            raise AppError(
                502, "embedding_failed", "The embedding provider returned an unexpected response"
            )
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
                choices = payload.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                text = delta.get("content")
                if isinstance(text, str) and text:
                    yield text


def get_embedding_client() -> EmbeddingClient:
    return OpenAICompatibleEmbeddingClient(get_settings())


def get_chat_client() -> ChatClient:
    return OpenAICompatibleChatClient(get_settings())
