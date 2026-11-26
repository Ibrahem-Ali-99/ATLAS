import json

import httpx
import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.integrations.language import OpenAICompatibleChatClient, OpenAICompatibleEmbeddingClient


def _configured():
    return get_settings().model_copy(
        update={"embedding_api_key": "test-key", "llm_api_key": "test-key"}
    )


def _vector(value: float) -> list[float]:
    return [value] * get_settings().embedding_dimensions


def test_injected_transport_covers_success_auth_timeout_and_network_failure() -> None:
    seen: list[str] = []

    def success(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n',
            request=request,
        )

    client = OpenAICompatibleChatClient(_configured(), transport=httpx.MockTransport(success))
    assert client.complete("system", "user") == "ok"
    assert seen == ["Bearer test-key"]

    unauthorized = httpx.MockTransport(lambda request: httpx.Response(401, request=request))
    with pytest.raises(AppError) as invalid:
        OpenAICompatibleChatClient(_configured(), transport=unauthorized).complete("system", "user")
    assert invalid.value.code == "llm_unauthorized"

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("test timeout", request=request)

    with pytest.raises(AppError) as timed_out:
        OpenAICompatibleChatClient(_configured(), transport=httpx.MockTransport(timeout)).complete(
            "system", "user"
        )
    assert timed_out.value.code == "llm_timeout"

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(AppError) as unavailable:
        OpenAICompatibleChatClient(_configured(), transport=httpx.MockTransport(offline)).complete(
            "system", "user"
        )
    assert unavailable.value.code == "llm_unavailable"


def test_embedding_transport_uses_the_secret_only_on_the_request() -> None:
    secret = "organization-secret-that-must-not-return"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {secret}"
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": _vector(0.1)}]},
            request=request,
        )

    client = OpenAICompatibleEmbeddingClient(
        _configured().model_copy(update={"embedding_api_key": secret}),
        transport=httpx.MockTransport(handler),
    )
    result = client.embed(["hello"])
    assert len(result[0]) == get_settings().embedding_dimensions
    assert secret not in repr(result)


class _Response:
    def __init__(self, status: int, payload: object) -> None:
        self.status_code = status
        self._payload = payload

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _Stream:
    def __init__(
        self, status: int, lines: list[str], headers: dict[str, str] | None = None
    ) -> None:
        self.status_code = status
        self._lines = lines
        self.headers = headers or {}

    def __enter__(self) -> "_Stream":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def iter_lines(self) -> list[str]:
        return self._lines


def test_empty_provider_keys_fail_before_a_request(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("provider was called")

    monkeypatch.setattr(httpx, "post", fail)
    monkeypatch.setattr(httpx, "stream", fail)
    with pytest.raises(AppError) as embedding_error:
        OpenAICompatibleEmbeddingClient(get_settings()).embed(["hello"])
    assert embedding_error.value.code == "embedding_unconfigured"
    with pytest.raises(AppError) as chat_error:
        OpenAICompatibleChatClient(get_settings()).complete("system", "user")
    assert chat_error.value.code == "llm_unconfigured"


def test_embedding_orders_vectors_and_rejects_malformed_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            _Response(
                200,
                {
                    "usage": {"prompt_tokens": 4, "total_tokens": 4},
                    "data": [
                        {"index": 1, "embedding": _vector(0.2)},
                        {"index": 0, "embedding": _vector(0.1)},
                    ],
                },
            ),
            _Response(200, {"data": "nope"}),
            _Response(200, {"data": [{"index": 0, "embedding": [0.1, 0.2]}]}),
            _Response(200, json.JSONDecodeError("bad", "doc", 0)),
            _Response(401, {"error": {"message": "no"}}),
        ]
    )
    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: next(responses))
    client = OpenAICompatibleEmbeddingClient(_configured())
    vectors = client.embed(["first", "second"])
    assert vectors[0][0] == 0.1
    assert vectors[1][0] == 0.2
    assert len(vectors[0]) == get_settings().embedding_dimensions
    expected = (
        "embedding_failed",
        "embedding_dimension_mismatch",
        "embedding_failed",
        "embedding_unauthorized",
    )
    for code in expected:
        with pytest.raises(AppError) as exc:
            client.embed(["hello"])
        assert exc.value.code == code


def test_usage_is_stored_under_the_model_that_produced_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[dict[str, object]] = []

    def capture(**kwargs: object) -> None:
        recorded.append(kwargs)

    monkeypatch.setattr("app.domains.observability.tracing.record_operation", capture)
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *_args, **_kwargs: _Response(
            200,
            {"usage": {"prompt_tokens": 3}, "data": [{"index": 0, "embedding": _vector(0.1)}]},
        ),
    )
    OpenAICompatibleEmbeddingClient(_configured()).embed(["hello"])
    monkeypatch.setattr(
        httpx,
        "stream",
        lambda *_args, **_kwargs: _Stream(
            200,
            [
                'data: {"choices":[{"delta":{"content":"Cold"}}],'
                '"usage":{"prompt_tokens":2,"completion_tokens":1}}',
                "data: [DONE]",
            ],
        ),
    )
    assert OpenAICompatibleChatClient(_configured()).complete("system", "user") == "Cold"
    settings = get_settings()
    assert recorded[0]["operation"] == "embedding_usage"
    assert recorded[0]["model_name"] == settings.embedding_model
    assert recorded[1]["operation"] == "llm_usage"
    assert recorded[1]["model_name"] == settings.llm_model


def test_chat_stream_yields_tokens_and_ignores_non_content_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.domains.observability.tracing.record_operation",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        httpx,
        "stream",
        lambda *_args, **_kwargs: _Stream(
            200,
            [
                ": keep-alive",
                "event: message",
                "",
                "data:",
                'data: {"choices":[{"delta":{"role":"assistant"}}]}',
                'data: {"choices":[{"delta":{"content":"Cold"}}]}',
                'data: {"choices":[{"delta":{"content":" storage"}}]}',
                'data: {"choices":[]}',
                'data: {"usage":{"prompt_tokens":2,"completion_tokens":2}}',
                "data: [DONE]",
                'data: {"choices":[{"delta":{"content":"ignored"}}]}',
            ],
        ),
    )
    client = OpenAICompatibleChatClient(_configured())
    assert list(client.stream("system", "user")) == ["Cold", " storage"]
    assert client.complete("system", "user") == "Cold storage"


def test_malformed_stream_data_is_a_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    streams = iter(
        [
            _Stream(
                200,
                [
                    'data: {"choices":[{"delta":{"content":"Cold"}}]}',
                    "data: not-json",
                    'data: {"choices":[{"delta":{"content":" storage"}}]}',
                ],
            ),
            _Stream(200, ["data: {"]),
        ]
    )
    monkeypatch.setattr(httpx, "stream", lambda *_args, **_kwargs: next(streams))
    client = OpenAICompatibleChatClient(_configured())
    chunks = client.stream("system", "user")
    assert next(chunks) == "Cold"
    with pytest.raises(AppError) as streamed:
        next(chunks)
    assert streamed.value.code == "llm_failed"
    with pytest.raises(AppError) as completed:
        client.complete("system", "user")
    assert completed.value.code == "llm_failed"


def test_chat_stream_rejects_provider_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    streams = iter(
        [
            _Stream(200, ['data: {"error":{"message":"bad"}}']),
            _Stream(200, ['data: ["nope"]']),
            _Stream(502, ["data: {}"]),
        ]
    )
    monkeypatch.setattr(httpx, "stream", lambda *_args, **_kwargs: next(streams))
    client = OpenAICompatibleChatClient(_configured())
    for _ in range(3):
        with pytest.raises(AppError) as exc:
            client.complete("system", "user")
        assert exc.value.code == "llm_failed"


def test_ollama_omits_the_api_key_and_the_dimensions_field(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def post(*_args: object, **kwargs: object) -> _Response:
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return _Response(200, {"data": [{"index": 0, "embedding": [0.1] * 768}]})

    monkeypatch.setattr(httpx, "post", post)
    settings = get_settings().model_copy(
        update={
            "embedding_provider": "ollama",
            "embedding_api_key": "",
            "embedding_base_url": "http://127.0.0.1:11434/v1",
            "embedding_model": "nomic-embed-text",
            "embedding_dimensions": 768,
        }
    )
    vectors = OpenAICompatibleEmbeddingClient(settings).embed(["harbor"])
    headers = captured["headers"]
    body = captured["json"]
    assert isinstance(headers, dict)
    assert isinstance(body, dict)
    assert "Authorization" not in headers
    assert "dimensions" not in body
    assert len(vectors[0]) == 768


def test_ollama_connect_error_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def post(*_args: object, **_kwargs: object) -> None:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", post)
    settings = get_settings().model_copy(
        update={
            "embedding_provider": "ollama",
            "embedding_dimensions": 768,
            "embedding_base_url": "http://127.0.0.1:11434/v1",
        }
    )
    with pytest.raises(AppError) as exc:
        OpenAICompatibleEmbeddingClient(settings).embed(["harbor"])
    assert exc.value.code == "embedding_unavailable"


def test_groq_asks_for_a_json_object_when_the_prompt_requires_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def stream(*_args: object, **kwargs: object) -> _Stream:
        captured["json"] = kwargs["json"]
        return _Stream(
            200,
            [
                'data: {"choices":[{"delta":{"content":"{\\"category\\":\\"warehousing\\"}"}}]}',
                "data: [DONE]",
            ],
        )

    monkeypatch.setattr(httpx, "stream", stream)
    monkeypatch.setattr(
        "app.domains.observability.tracing.record_operation", lambda **_kwargs: None
    )
    settings = get_settings().model_copy(
        update={
            "llm_provider": "groq",
            "llm_api_key": "test-key",
            "llm_base_url": "https://api.groq.com/openai/v1",
            "llm_model": "openai/gpt-oss-20b",
        }
    )
    text = OpenAICompatibleChatClient(settings).complete("Return one JSON object", "hello")
    body = captured["json"]
    assert isinstance(body, dict)
    assert body["response_format"] == {"type": "json_object"}
    assert body["model"] == "openai/gpt-oss-20b"
    assert "category" in text


def test_chat_retries_a_rate_limit_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}
    waits: list[float] = []
    monkeypatch.setattr("app.integrations.language.time.sleep", waits.append)
    monkeypatch.setattr(
        "app.domains.observability.tracing.record_operation", lambda **_kwargs: None
    )

    def stream(*_args: object, **_kwargs: object) -> _Stream:
        calls["count"] += 1
        if calls["count"] == 1:
            return _Stream(429, [], {"retry-after": "1.5"})
        return _Stream(200, ['data: {"choices":[{"delta":{"content":"ok"}}]}', "data: [DONE]"])

    monkeypatch.setattr(httpx, "stream", stream)
    client = OpenAICompatibleChatClient(_configured())
    assert client.complete("system", "user") == "ok"
    assert calls["count"] == 2
    assert waits == [1.5]
    calls["count"] = 0
    waits.clear()

    def always_limited(*_args: object, **_kwargs: object) -> _Stream:
        calls["count"] += 1
        return _Stream(429, [])

    monkeypatch.setattr(httpx, "stream", always_limited)
    with pytest.raises(AppError) as exc:
        client.complete("system", "user")
    assert exc.value.code == "llm_rate_limited"
    assert calls["count"] == 3
    assert len(waits) == 2

    calls["count"] = 0

    def unauthorized(*_args: object, **_kwargs: object) -> _Stream:
        calls["count"] += 1
        return _Stream(401, [])

    monkeypatch.setattr(httpx, "stream", unauthorized)
    with pytest.raises(AppError) as denied:
        client.complete("system", "user")
    assert denied.value.code == "llm_unauthorized"
    assert calls["count"] == 1


def test_chat_timeout_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    def stream(*_args: object, **_kwargs: object) -> None:
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(httpx, "stream", stream)
    client = OpenAICompatibleChatClient(_configured())
    with pytest.raises(AppError) as exc:
        client.complete("system", "user")
    assert exc.value.code == "llm_timeout"
