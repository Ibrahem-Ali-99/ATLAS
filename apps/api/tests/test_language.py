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


class _Response:
    def __init__(self, status: int, payload: object) -> None:
        self.status_code = status
        self._payload = payload

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _Stream:
    def __init__(self, status: int, lines: list[str]) -> None:
        self.status_code = status
        self._lines = lines

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
    for _ in range(4):
        with pytest.raises(AppError) as exc:
            client.embed(["hello"])
        assert exc.value.code == "embedding_failed"


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
