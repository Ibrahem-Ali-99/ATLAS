"""Opt-in Groq and Ollama smoke. Prints status only, never a key or a prompt."""

from __future__ import annotations

import time

import httpx

from app.core.config import ENV_FILE
from app.core.errors import AppError
from app.integrations.language import OpenAICompatibleChatClient, OpenAICompatibleEmbeddingClient


def main() -> None:
    values = _file_values()
    if not values.get("ATLAS_LLM_API_KEY", "").strip():
        raise SystemExit("live Groq verification is blocked: the local key is absent")
    from app.core.config import Settings

    settings = Settings(
        _env_file=None,
        environment="development",
        secret_key="live-provider-check-secret-key-value",
        database_url="postgresql+psycopg://atlas:atlas@localhost:5432/atlas",
        llm_provider="groq",
        llm_base_url=values.get("ATLAS_LLM_BASE_URL", "https://api.groq.com/openai/v1"),
        llm_api_key=values["ATLAS_LLM_API_KEY"],
        llm_model=values.get("ATLAS_LLM_MODEL", "openai/gpt-oss-20b"),
        embedding_provider="ollama",
        embedding_base_url=values.get("ATLAS_EMBEDDING_BASE_URL", "http://127.0.0.1:11434/v1"),
        embedding_model=values.get("ATLAS_EMBEDDING_MODEL", "nomic-embed-text"),
        embedding_dimensions=int(values.get("ATLAS_EMBEDDING_DIMENSIONS", "768")),
    )
    started = time.perf_counter()
    answer = OpenAICompatibleChatClient(settings).complete(
        "Reply with one short sentence.",
        "Say ready.",
    )
    print("groq_ms", round((time.perf_counter() - started) * 1000))
    print("groq_nonempty", bool(answer.strip()))
    print("groq_safe", "gsk_" not in answer)
    started = time.perf_counter()
    vectors = OpenAICompatibleEmbeddingClient(settings).embed(["harbor", "bonded yard"])
    print("ollama_ms", round((time.perf_counter() - started) * 1000))
    print("ollama_width", [len(vector) for vector in vectors])
    numeric = all(all(isinstance(value, float) for value in vector) for vector in vectors)
    print("ollama_numeric", numeric)
    try:
        OpenAICompatibleEmbeddingClient(
            settings.model_copy(update={"embedding_base_url": "http://127.0.0.1:9/v1"})
        ).embed(["harbor"])
    except AppError as exc:
        print("ollama_down", exc.code)
    else:
        raise SystemExit("closed port unexpectedly returned an embedding")


def _file_values() -> dict[str, str]:
    if ENV_FILE is None or not ENV_FILE.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as exc:
        raise SystemExit(exc.__class__.__name__) from exc
