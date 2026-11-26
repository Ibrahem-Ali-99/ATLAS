import json
from collections.abc import Iterator
from typing import Any, Protocol

import httpx
import structlog

from app.core.config import Settings, get_settings
from app.core.errors import AppError

logger = structlog.get_logger(__name__)
HttpTransport = httpx.BaseTransport


class EmbeddingClient(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ChatClient(Protocol):
    def ensure_configured(self) -> None: ...

    def complete(self, system: str, user: str) -> str: ...

    def stream(self, system: str, user: str) -> Iterator[str]: ...


class OpenAICompatibleEmbeddingClient:
    def __init__(self, settings: Settings, *, transport: HttpTransport | None = None) -> None:
        self._settings = settings
        self._transport = transport

    @property
    def settings(self) -> Settings:
        return self._settings

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        needs_key = self._settings.embedding_provider != "ollama"
        if needs_key and not self._settings.embedding_api_key.strip():
            raise AppError(
                503,
                "embedding_unconfigured",
                "The embedding provider is not configured. Set ATLAS_EMBEDDING_API_KEY.",
            )
        body: dict[str, Any] = {
            "model": self._settings.embedding_model,
            "input": texts,
        }
        if self._settings.embedding_provider == "openai":
            body["dimensions"] = self._settings.embedding_dimensions
        response = _post_with_retry(
            f"{self._settings.embedding_base_url.rstrip('/')}/embeddings",
            headers=_bearer(self._settings.embedding_api_key),
            body=body,
            timeout=self._settings.embedding_timeout_seconds,
            unavailable="embedding_unavailable",
            timeout_code="embedding_timeout",
            rate_code="embedding_rate_limited",
            unavailable_message=_embedding_unavailable_message(self._settings),
            transport=self._transport,
        )
        _raise_for_provider_status(response.status_code, kind="embedding")
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise AppError(
                502, "embedding_failed", "The embedding provider returned an unexpected response"
            ) from exc
        vectors = _embedding_vectors(payload, len(texts), self._settings.embedding_dimensions)
        _log_usage("embedding_usage", payload, self._settings.embedding_provider)
        return vectors


class OpenAICompatibleChatClient:
    def __init__(self, settings: Settings, *, transport: HttpTransport | None = None) -> None:
        self._settings = settings
        self._transport = transport
        self._output_limit: int | None = None

    def limit_output(self, tokens: int) -> None:
        self._output_limit = tokens

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
        for attempt in range(2):
            yielded = False
            try:
                for token in self._read_stream(system, user):
                    yielded = True
                    yield token
                return
            except AppError as exc:
                if yielded or attempt == 1 or exc.code not in {"llm_rate_limited", "llm_timeout"}:
                    raise
            except httpx.TimeoutException as exc:
                if yielded or attempt == 1:
                    raise AppError(504, "llm_timeout", "The language model timed out.") from exc
            except httpx.ConnectError as exc:
                raise AppError(
                    503, "llm_unavailable", "The language model could not be reached."
                ) from exc

    def _read_stream(self, system: str, user: str) -> Iterator[str]:
        body: dict[str, Any] = {
            "model": self._settings.llm_model,
            "stream": True,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        output_limit = self._output_limit
        if output_limit is None:
            output_limit = self._settings.llm_max_output_tokens
        if output_limit is not None:
            body["max_tokens"] = output_limit
        if "json" in system.lower():
            body["response_format"] = {"type": "json_object"}
        if self._transport is None:
            response_context = httpx.stream(
                "POST",
                f"{self._settings.llm_base_url.rstrip('/')}/chat/completions",
                headers=_bearer(self._settings.llm_api_key),
                json=body,
                timeout=self._settings.llm_timeout_seconds,
            )
        else:
            client = httpx.Client(
                transport=self._transport, timeout=self._settings.llm_timeout_seconds
            )
            response_context = client.stream(
                "POST",
                f"{self._settings.llm_base_url.rstrip('/')}/chat/completions",
                headers=_bearer(self._settings.llm_api_key),
                json=body,
            )
        with response_context as response:
            _raise_for_provider_status(response.status_code, kind="llm")
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if not data:
                    continue
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise AppError(
                        502, "llm_failed", "The language model returned an unexpected response"
                    ) from exc
                if not isinstance(payload, dict):
                    raise AppError(
                        502, "llm_failed", "The language model returned an unexpected response"
                    )
                _log_usage("llm_usage", payload, self._settings.llm_provider)
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
        if not isinstance(vector, list) or any(type(value) not in {int, float} for value in vector):
            raise AppError(
                502, "embedding_failed", "The embedding provider returned an unexpected response"
            )
        if len(vector) != dimensions:
            raise AppError(
                502,
                "embedding_dimension_mismatch",
                (
                    f"The embedding provider returned {len(vector)} values, "
                    f"and this deployment expects {dimensions}."
                ),
            )
        vectors.append([float(value) for value in vector])
    if len(vectors) != count:
        raise AppError(
            502, "embedding_failed", "The embedding provider returned an unexpected response"
        )
    return vectors


def _log_usage(event: str, payload: dict[str, Any], provider: str) -> None:
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
        provider=provider,
        model_name=settings.llm_model if event == "llm_usage" else settings.embedding_model,
        tokens_in=prompt if isinstance(prompt, int) else None,
        tokens_out=completion if isinstance(completion, int) else None,
    )


def _bearer(api_key: str) -> dict[str, str]:
    if not api_key.strip():
        return {}
    return {"Authorization": f"Bearer {api_key}"}


def _embedding_unavailable_message(settings: Settings) -> str:
    if settings.embedding_provider == "ollama":
        return "Ollama is not running at the configured address."
    return "The embedding provider could not be reached."


def _raise_for_provider_status(status: int, *, kind: str) -> None:
    if status < 400:
        return
    if kind == "embedding":
        if status in {401, 403}:
            raise AppError(
                503, "embedding_unauthorized", "The embedding provider rejected the API key."
            )
        if status == 429:
            raise AppError(
                503,
                "embedding_rate_limited",
                "The embedding provider rate limit was reached. Wait and try again.",
            )
        if status == 404:
            raise AppError(503, "embedding_unavailable", "The embedding model was not found.")
        raise AppError(502, "embedding_failed", "The embedding provider rejected the request")
    if status in {401, 403}:
        raise AppError(503, "llm_unauthorized", "The language model rejected the API key.")
    if status == 429:
        raise AppError(
            503,
            "llm_rate_limited",
            "The language model rate limit was reached. Wait and try again.",
        )
    if status == 404:
        raise AppError(503, "llm_unavailable", "The language model was not found.")
    raise AppError(502, "llm_failed", "The language model rejected the request")


def _post_with_retry(
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float,
    unavailable: str,
    timeout_code: str,
    rate_code: str,
    unavailable_message: str,
    transport: HttpTransport | None = None,
) -> httpx.Response:
    response: httpx.Response | None = None
    for attempt in range(2):
        try:
            if transport is None:
                response = httpx.post(url, headers=headers, json=body, timeout=timeout)
            else:
                with httpx.Client(transport=transport, timeout=timeout) as client:
                    response = client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            if attempt == 1:
                raise AppError(504, timeout_code, "The embedding provider timed out.") from exc
            continue
        except httpx.ConnectError as exc:
            raise AppError(503, unavailable, unavailable_message) from exc
        if response.status_code in {429, 503} and attempt == 0:
            continue
        if response.status_code == 429:
            raise AppError(
                503, rate_code, "The embedding provider rate limit was reached. Wait and try again."
            )
        return response
    if response is None:
        raise AppError(504, timeout_code, "The embedding provider timed out.")
    return response


def get_embedding_client(
    db: Any = None, organization_id: Any = None, *, for_verification: bool = False
) -> EmbeddingClient:
    settings = get_settings()
    if db is not None and organization_id is not None:
        from app.domains.demo.access import organization_is_visitor

        if organization_is_visitor(db, organization_id):
            from app.integrations.doubles import DeterministicEmbeddingClient

            return DeterministicEmbeddingClient()
        from app.integrations.resolver import resolve_settings

        settings = resolve_settings(
            db, organization_id, "embedding", for_verification=for_verification
        )
    if settings.public_demo and settings.embedding_provider != "double":
        raise AppError(
            503,
            "embedding_unconfigured",
            "External model calls are disabled for this deployment.",
        )
    if settings.embedding_provider == "double":
        from app.integrations.doubles import DeterministicEmbeddingClient

        return DeterministicEmbeddingClient()
    return OpenAICompatibleEmbeddingClient(settings)


def get_chat_client(
    db: Any = None,
    organization_id: Any = None,
    *,
    for_verification: bool = False,
    max_output_tokens: int | None = None,
) -> ChatClient:
    settings = get_settings()
    if db is not None and organization_id is not None:
        from app.domains.demo.access import organization_is_visitor

        if organization_is_visitor(db, organization_id):
            from app.integrations.doubles import DeterministicChatClient

            return DeterministicChatClient()
        from app.integrations.resolver import resolve_settings

        settings = resolve_settings(db, organization_id, "chat", for_verification=for_verification)
    if settings.public_demo and settings.llm_provider != "double":
        raise AppError(
            503,
            "llm_unconfigured",
            "External model calls are disabled for this deployment.",
        )
    if settings.llm_provider == "double":
        from app.integrations.doubles import DeterministicChatClient

        return DeterministicChatClient()
    client = OpenAICompatibleChatClient(settings)
    if max_output_tokens is not None:
        client.limit_output(max_output_tokens)
    return client
