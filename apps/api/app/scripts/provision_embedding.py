"""Install the staging embedding model once and check its vector width.

A model that is already present is not downloaded again. The OpenAI provider
skips the pull and keeps the 1536-dimensional column available. This command
does not read or write application rows.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Protocol

from app.domains.knowledge.chunking import chunk_pages

PINNED_OLLAMA_MODEL = "nomic-embed-text:v1.5"
PINNED_WIDTH = 768
OPENAI_WIDTH = 1536
_PROBE = "Harbor Freight Logistics invoice 1842 covers the March warehouse transfer."
_QUERY = "Which invoice covers the March warehouse transfer?"
_DISTRACTOR = "The greenhouse tomatoes were watered on Tuesday morning."


class EmbeddingProvisionError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class EmbeddingClient(Protocol):
    def get_json(self, url: str) -> dict[str, object]: ...

    def post_json(self, url: str, body: dict[str, object]) -> dict[str, object]: ...


def ollama_root(base_url: str) -> str:
    root = base_url.strip().rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return root


def model_is_present(names: list[str], model: str) -> bool:
    return model in names


def parse_model_names(payload: dict[str, object]) -> list[str]:
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    names: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name:
            names.append(name)
    return names


def vector_width(payload: dict[str, object]) -> int:
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise EmbeddingProvisionError("embedding_empty")
    first = data[0]
    if not isinstance(first, dict):
        raise EmbeddingProvisionError("embedding_empty")
    embedding = first.get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise EmbeddingProvisionError("embedding_empty")
    return len(embedding)


def embedding_rows(payload: dict[str, object]) -> list[list[float]]:
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise EmbeddingProvisionError("embedding_empty")
    rows: list[list[float]] = []
    for item in data:
        if not isinstance(item, dict):
            raise EmbeddingProvisionError("embedding_empty")
        embedding = item.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise EmbeddingProvisionError("embedding_empty")
        rows.append([float(value) for value in embedding])
    return rows


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise EmbeddingProvisionError("embedding_dimension_mismatch")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise EmbeddingProvisionError("embedding_empty")
    return dot / (left_norm * right_norm)


def synthetic_chunks() -> list[str]:
    pages: list[tuple[int | None, str]] = [(1, (_PROBE + " ") * 40)]
    return [piece.content for piece in chunk_pages(pages)]


def _expected_width(provider: str, model: str, dimensions: int) -> int | None:
    if provider == "openai":
        if dimensions not in (PINNED_WIDTH, OPENAI_WIDTH):
            raise EmbeddingProvisionError(
                f"embedding_dimension_mismatch width={dimensions} expected=768|1536"
            )
        return None
    if provider != "ollama":
        raise EmbeddingProvisionError(f"embedding_provider_unsupported provider={provider}")
    if model == PINNED_OLLAMA_MODEL and dimensions != PINNED_WIDTH:
        raise EmbeddingProvisionError(
            f"embedding_dimension_mismatch width={dimensions} expected={PINNED_WIDTH} "
            "nomic-embed-text:v1.5 writes chunks.embedding_768"
        )
    if dimensions not in (PINNED_WIDTH, OPENAI_WIDTH):
        raise EmbeddingProvisionError(
            f"embedding_dimension_mismatch width={dimensions} expected=768|1536"
        )
    return dimensions


def _tags(
    client: EmbeddingClient, url: str, attempts: int, pause_seconds: float
) -> dict[str, object]:
    last = "embedding_unavailable Ollama is not running at the configured address."
    for attempt in range(attempts):
        try:
            return client.get_json(url)
        except EmbeddingProvisionError as exc:
            if "status=" in exc.reason:
                raise
            last = exc.reason
            if attempt + 1 >= attempts:
                raise EmbeddingProvisionError(last) from exc
            time.sleep(pause_seconds)
    raise EmbeddingProvisionError(last)


def provision(
    *,
    provider: str,
    base_url: str,
    model: str,
    dimensions: int,
    client: EmbeddingClient,
    attempts: int = 1,
    pause_seconds: float = 0,
) -> str:
    expected = _expected_width(provider, model, dimensions)
    if expected is None:
        return f"embedding_skipped provider=openai dimensions={dimensions}"
    root = ollama_root(base_url)
    if not root:
        raise EmbeddingProvisionError(
            "embedding_unavailable Ollama is not running at the configured address."
        )
    tags = _tags(client, f"{root}/api/tags", attempts, pause_seconds)
    present = model_is_present(parse_model_names(tags), model)
    pulled = False
    if not present:
        client.post_json(f"{root}/api/pull", {"name": model, "stream": False})
        pulled = True
    payload = client.post_json(
        f"{root}/v1/embeddings",
        {"model": model, "input": [_PROBE]},
    )
    width = vector_width(payload)
    if width != expected:
        raise EmbeddingProvisionError(
            f"embedding_dimension_mismatch width={width} expected={expected}"
        )
    chunks = synthetic_chunks()
    indexed = client.post_json(f"{root}/v1/embeddings", {"model": model, "input": chunks})
    for row in embedding_rows(indexed):
        if len(row) != expected:
            raise EmbeddingProvisionError(
                f"embedding_dimension_mismatch width={len(row)} expected={expected}"
            )
    ranked = client.post_json(
        f"{root}/v1/embeddings",
        {"model": model, "input": [_QUERY, _PROBE, _DISTRACTOR]},
    )
    query, relevant, distractor = embedding_rows(ranked)
    if cosine(query, relevant) <= cosine(query, distractor):
        raise EmbeddingProvisionError(
            "embedding_probe_failed the pinned model did not rank the matching passage first"
        )
    pulled_flag = str(pulled).lower()
    return f"embedding_ok model={model} width={width} chunks={len(chunks)} pulled={pulled_flag}"


class UrllibEmbeddingClient:
    def get_json(self, url: str) -> dict[str, object]:
        return _request("GET", url, None, 10)

    def post_json(self, url: str, body: dict[str, object]) -> dict[str, object]:
        timeout = 600 if url.endswith("/api/pull") else 180
        return _request("POST", url, body, timeout)


def _request(
    method: str, url: str, body: dict[str, object] | None, timeout: float
) -> dict[str, object]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if data is not None else {}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read(300).decode("utf-8", "replace")
        if exc.code == 404:
            raise EmbeddingProvisionError(
                "embedding_unavailable The embedding model was not found."
            ) from exc
        raise EmbeddingProvisionError(
            f"embedding_unavailable status={exc.code} {detail[:180]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise EmbeddingProvisionError(
            f"embedding_unavailable Ollama is not running at the configured address. {exc.reason}"
        ) from exc
    return _decode(raw, url.endswith("/api/pull"))


def _decode(raw: bytes, pull: bool) -> dict[str, object]:
    text = raw.decode("utf-8", "replace").strip()
    if not text:
        raise EmbeddingProvisionError(
            "embedding_unavailable The embedding service returned an empty response."
        )
    line = text.splitlines()[-1] if pull else text
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise EmbeddingProvisionError(
            "embedding_unavailable The embedding service returned an unreadable response."
        ) from exc
    if not isinstance(payload, dict):
        raise EmbeddingProvisionError(
            "embedding_unavailable The embedding service returned an unreadable response."
        )
    error = payload.get("error")
    if isinstance(error, str) and error:
        raise EmbeddingProvisionError(f"embedding_unavailable {error[:180]}")
    return payload


def main() -> int:
    provider = os.environ.get("ATLAS_EMBEDDING_PROVIDER", "openai")
    base_url = os.environ.get("ATLAS_EMBEDDING_BASE_URL", "")
    model = os.environ.get("ATLAS_EMBEDDING_MODEL", PINNED_OLLAMA_MODEL)
    try:
        dimensions = int(os.environ.get("ATLAS_EMBEDDING_DIMENSIONS", str(OPENAI_WIDTH)))
        line = provision(
            provider=provider,
            base_url=base_url,
            model=model,
            dimensions=dimensions,
            client=UrllibEmbeddingClient(),
            attempts=30,
            pause_seconds=2,
        )
    except EmbeddingProvisionError as exc:
        print(exc.reason, file=sys.stderr)
        return 1
    except ValueError:
        print("embedding_dimension_mismatch width=invalid", file=sys.stderr)
        return 1
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
