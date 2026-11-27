import json
import random
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx
import structlog

from app.core.config import Settings, get_settings
from app.core.errors import AppError

logger = structlog.get_logger(__name__)
HttpTransport = httpx.BaseTransport
_MAX_PROVIDER_ATTEMPTS = 3
_MAX_RETRY_WAIT = 8.0
_TRANSIENT_LLM = {"llm_rate_limited", "llm_timeout"}
_LOCAL_MODEL_HOSTS = frozenset({"ollama", "localhost", "127.0.0.1", "host.docker.internal", "::1"})


def local_model_endpoint(url: str) -> bool:
    """True when the chat URL stays on the private network or loopback."""

    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host in _LOCAL_MODEL_HOSTS


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    """Honor Retry-After, otherwise wait with exponential backoff and jitter."""

    if response is not None:
        raw = response.headers.get("retry-after")
        if raw:
            try:
                return min(max(float(raw), 0.0), _MAX_RETRY_WAIT)
            except ValueError:
                pass
    base = 0.4 * (2**attempt)
    return min(base + random.uniform(0, 0.2), _MAX_RETRY_WAIT)


class EmbeddingClient(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ChatClient(Protocol):
    def ensure_configured(self) -> None: ...

    def complete(self, system: str, user: str) -> str: ...

    def stream(self, system: str, user: str) -> Iterator[str]: ...


@dataclass(frozen=True)
class ModelToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ModelToolResult:
    content: str | None
    tool_calls: list[ModelToolCall]
    prompt_tokens: int | None
    completion_tokens: int | None


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
        self._reasoning_effort: str | None = None
        self._retry_delay = 0.0
        self._keyless_local = False
        self.last_usage: tuple[int | None, int | None] | None = None

    def permit_keyless_local(self) -> None:
        """Allow an empty key for a visitor call to a private model endpoint."""

        self._keyless_local = True

    def prefer_brief_reply(self) -> None:
        """Cap a conversational reply so a greeting does not wait on a long trace."""

        if self._output_limit is None:
            self._output_limit = 400
        self._reasoning_effort = "low"

    def limit_output(self, tokens: int) -> None:
        self._output_limit = tokens

    def ensure_configured(self) -> None:
        if self._settings.llm_api_key.strip():
            return
        if self._keyless_local and local_model_endpoint(self._settings.llm_base_url):
            return
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
        for attempt in range(_MAX_PROVIDER_ATTEMPTS):
            yielded = False
            self._retry_delay = 0.0
            try:
                for token in self._read_stream(system, user, attempt):
                    yielded = True
                    yield token
                return
            except AppError as exc:
                if (
                    yielded
                    or attempt == _MAX_PROVIDER_ATTEMPTS - 1
                    or exc.code not in _TRANSIENT_LLM
                ):
                    raise
                time.sleep(self._retry_delay or _retry_delay(None, attempt))
            except httpx.TimeoutException as exc:
                if yielded or attempt == _MAX_PROVIDER_ATTEMPTS - 1:
                    raise AppError(504, "llm_timeout", "The language model timed out.") from exc
                time.sleep(_retry_delay(None, attempt))
            except httpx.ConnectError as exc:
                raise AppError(
                    503, "llm_unavailable", "The language model could not be reached."
                ) from exc

    def _read_stream(self, system: str, user: str, attempt: int = 0) -> Iterator[str]:
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
        _set_reasoning(body, self._settings.llm_model, self._reasoning_effort)
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
            if response.status_code in {429, 503}:
                self._retry_delay = _retry_delay(response, attempt)
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
                self.last_usage = _usage_pair(payload)
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

    def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        tool_choice: str = "auto",
        reasoning_effort: str | None = None,
    ) -> ModelToolResult:
        """One non-streaming tool-calling turn. Reasoning fields are discarded."""

        self.ensure_configured()
        body: dict[str, Any] = {
            "model": self._settings.llm_model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
        }
        output_limit = self._output_limit
        if output_limit is None:
            output_limit = self._settings.llm_max_output_tokens
        if output_limit is not None:
            body["max_tokens"] = output_limit
        _set_reasoning(body, self._settings.llm_model, reasoning_effort or self._reasoning_effort)
        response: httpx.Response | None = None
        for attempt in range(_MAX_PROVIDER_ATTEMPTS):
            try:
                response = _post_chat(self, body)
            except AppError as exc:
                if attempt == _MAX_PROVIDER_ATTEMPTS - 1 or exc.code not in _TRANSIENT_LLM:
                    raise
                time.sleep(_retry_delay(None, attempt))
                continue
            if response.status_code in {429, 503} and attempt < _MAX_PROVIDER_ATTEMPTS - 1:
                time.sleep(_retry_delay(response, attempt))
                continue
            break
        if response is None:
            raise AppError(504, "llm_timeout", "The language model timed out.")
        _raise_for_provider_status(response.status_code, kind="llm")
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise AppError(
                502, "llm_failed", "The language model returned an unexpected response"
            ) from exc
        if not isinstance(payload, dict):
            raise AppError(502, "llm_failed", "The language model returned an unexpected response")
        _log_usage("llm_usage", payload, self._settings.llm_provider)
        return _tool_result(payload)


def _post_chat(client: OpenAICompatibleChatClient, body: dict[str, Any]) -> httpx.Response:
    url = f"{client._settings.llm_base_url.rstrip('/')}/chat/completions"
    headers = _bearer(client._settings.llm_api_key)
    timeout = client._settings.llm_timeout_seconds
    try:
        if client._transport is None:
            return httpx.post(url, headers=headers, json=body, timeout=timeout)
        with httpx.Client(transport=client._transport, timeout=timeout) as http:
            return http.post(url, headers=headers, json=body)
    except httpx.TimeoutException as exc:
        raise AppError(504, "llm_timeout", "The language model timed out.") from exc
    except httpx.ConnectError as exc:
        raise AppError(503, "llm_unavailable", "The language model could not be reached.") from exc


def _tool_result(payload: dict[str, Any]) -> ModelToolResult:
    if isinstance(payload.get("error"), dict):
        raise AppError(502, "llm_failed", "The language model returned an unexpected response")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise AppError(502, "llm_failed", "The language model returned an unexpected response")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise AppError(502, "llm_failed", "The language model returned an unexpected response")
    content = message.get("content")
    text = content.strip() if isinstance(content, str) and content.strip() else None
    calls: list[ModelToolCall] = []
    raw_calls = message.get("tool_calls")
    if isinstance(raw_calls, list):
        for index, raw in enumerate(raw_calls):
            parsed = _one_tool_call(raw, index)
            if parsed is not None:
                calls.append(parsed)
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    return ModelToolResult(
        content=text,
        tool_calls=calls,
        prompt_tokens=prompt if isinstance(prompt, int) else None,
        completion_tokens=completion if isinstance(completion, int) else None,
    )


def _one_tool_call(raw: object, index: int) -> ModelToolCall | None:
    if not isinstance(raw, dict):
        return None
    function = raw.get("function")
    if not isinstance(function, dict):
        return None
    name = function.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    arguments = function.get("arguments")
    if isinstance(arguments, dict):
        encoded = json.dumps(arguments, default=str)
    elif isinstance(arguments, str):
        encoded = arguments
    else:
        encoded = "{}"
    call_id = raw.get("id")
    identifier = call_id if isinstance(call_id, str) and call_id else f"call_{index}"
    return ModelToolCall(id=identifier[:80], name=name.strip()[:80], arguments=encoded[:4000])


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


def _set_reasoning(body: dict[str, Any], model: str, effort: str | None) -> None:
    if effort and "gpt-oss" in model:
        body["reasoning_effort"] = effort


def _usage_pair(payload: dict[str, Any]) -> tuple[int | None, int | None] | None:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    return (
        prompt if isinstance(prompt, int) else None,
        completion if isinstance(completion, int) else None,
    )


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
    for attempt in range(_MAX_PROVIDER_ATTEMPTS):
        try:
            if transport is None:
                response = httpx.post(url, headers=headers, json=body, timeout=timeout)
            else:
                with httpx.Client(transport=transport, timeout=timeout) as client:
                    response = client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            if attempt == _MAX_PROVIDER_ATTEMPTS - 1:
                raise AppError(504, timeout_code, "The embedding provider timed out.") from exc
            time.sleep(_retry_delay(None, attempt))
            continue
        except httpx.ConnectError as exc:
            raise AppError(503, unavailable, unavailable_message) from exc
        if response.status_code in {429, 503} and attempt < _MAX_PROVIDER_ATTEMPTS - 1:
            time.sleep(_retry_delay(response, attempt))
            continue
        if response.status_code == 429:
            raise AppError(
                503, rate_code, "The embedding provider rate limit was reached. Wait and try again."
            )
        return response
    if response is None:
        raise AppError(504, timeout_code, "The embedding provider timed out.")
    return response


def public_chat_settings(settings: Settings) -> Settings:
    """Chat settings that carry only the public Groq credential."""

    return settings.model_copy(
        update={
            "llm_provider": "groq",
            "llm_base_url": settings.public_llm_base_url,
            "llm_api_key": settings.public_llm_api_key,
            "llm_model": settings.public_llm_model,
            "public_llm_api_key": "",
            "public_llm_authorized": False,
            "public_demo": False,
        }
    )


def public_embedding_settings(settings: Settings) -> Settings:
    """Embedding settings that carry only the public retrieval credential."""

    return settings.model_copy(
        update={
            "embedding_provider": settings.public_embedding_provider,
            "embedding_base_url": settings.public_embedding_base_url,
            "embedding_api_key": settings.public_embedding_api_key,
            "embedding_model": settings.public_embedding_model,
            "embedding_dimensions": settings.public_embedding_dimensions,
            "public_embedding_api_key": "",
            "public_embedding_authorized": False,
            "public_demo": False,
        }
    )


def get_embedding_client(
    db: Any = None, organization_id: Any = None, *, for_verification: bool = False
) -> EmbeddingClient:
    settings = get_settings()
    if db is not None and organization_id is not None:
        from app.domains.demo.access import organization_is_visitor

        if organization_is_visitor(db, organization_id):
            if settings.public_embedding_authorized:
                if not settings.public_embedding_api_key.strip():
                    raise AppError(
                        503,
                        "embedding_unconfigured",
                        "Public semantic retrieval is not configured.",
                    )
                return OpenAICompatibleEmbeddingClient(public_embedding_settings(settings))
            from app.domains.knowledge.semantic import VisitorSemanticEmbedder

            return VisitorSemanticEmbedder(db, organization_id)
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
    public_inference: bool = False,
) -> ChatClient:
    settings = get_settings()
    if db is not None and organization_id is not None:
        from app.domains.demo.access import organization_is_visitor

        if organization_is_visitor(db, organization_id):
            if (
                public_inference
                and settings.public_inference_enabled
                and settings.public_llm_authorized
            ):
                if not settings.public_llm_api_key.strip():
                    raise AppError(
                        503,
                        "llm_unconfigured",
                        "Public model replies are not configured.",
                    )
                client = OpenAICompatibleChatClient(public_chat_settings(settings))
                client.limit_output(
                    max_output_tokens
                    if max_output_tokens is not None
                    else settings.public_inference_max_output_tokens
                )
                return client
            if (
                public_inference
                and settings.public_inference_enabled
                and not settings.llm_api_key.strip()
                and local_model_endpoint(settings.llm_base_url)
            ):
                client = OpenAICompatibleChatClient(settings)
                client.permit_keyless_local()
                client.limit_output(
                    max_output_tokens
                    if max_output_tokens is not None
                    else settings.public_inference_max_output_tokens
                )
                return client
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
