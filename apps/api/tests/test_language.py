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


def test_chat_stream_keeps_tokens_and_rejects_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streams = iter(
        [
            _Stream(
                200,
                [
                    'data: {"choices":[{"delta":{"content":"Cold"}}]}',
                    "data: not-json",
                    'data: {"usage":{"prompt_tokens":2,"completion_tokens":1,"total_tokens":3}}',
                    "data: [DONE]",
                ],
            ),
            _Stream(200, ['data: {"error":{"message":"bad"}}']),
            _Stream(200, ['data: ["nope"]']),
            _Stream(502, ["data: {}"]),
        ]
    )
    monkeypatch.setattr(httpx, "stream", lambda *_args, **_kwargs: next(streams))
    client = OpenAICompatibleChatClient(_configured())
    assert client.complete("system", "user") == "Cold"
    for _ in range(3):
        with pytest.raises(AppError) as exc:
            client.complete("system", "user")
        assert exc.value.code == "llm_failed"
