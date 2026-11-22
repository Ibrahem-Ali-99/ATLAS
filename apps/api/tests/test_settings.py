import uuid

import pytest
from pydantic import ValidationError
from starlette.responses import Response

from app.core.config import Settings, get_settings
from app.core.security import attach_session_cookie


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "secret_key": "test-secret-key-must-be-32-chars-min",
        "database_url": "postgresql+psycopg://atlas:atlas@localhost:5432/atlas_test",
        "cookie_secure": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_secret_key_must_be_at_least_32_characters() -> None:
    with pytest.raises(ValidationError):
        _settings(secret_key="too-short")


def test_production_rejects_placeholder_secret() -> None:
    with pytest.raises(ValidationError):
        _settings(
            environment="production",
            secret_key="replace-with-a-long-random-string",
            cookie_secure=True,
        )


def test_production_requires_secure_cookies() -> None:
    with pytest.raises(ValidationError):
        _settings(
            environment="production",
            secret_key="a-real-production-secret-key-value",
            cookie_secure=False,
        )


def test_public_demo_refuses_paid_calls_and_external_effects() -> None:
    with pytest.raises(ValidationError):
        _settings(public_demo=True, llm_api_key="sk-test")
    with pytest.raises(ValidationError):
        _settings(public_demo=True, n8n_lead_webhook_url="http://n8n/hook")
    with pytest.raises(ValidationError):
        _settings(public_demo=True, email_mode="live", email_live_enabled=True)


def test_public_demo_blocks_the_paid_chat_client(monkeypatch) -> None:
    from app.core.errors import AppError
    from app.integrations.language import get_chat_client

    demo = get_settings().model_copy(update={"public_demo": True, "llm_provider": "openai"})
    monkeypatch.setattr("app.integrations.language.get_settings", lambda: demo)
    with pytest.raises(AppError) as caught:
        get_chat_client()
    assert caught.value.code == "llm_unconfigured"


def test_embedding_width_accepts_the_two_stored_columns() -> None:
    assert _settings(embedding_dimensions=768).embedding_dimensions == 768
    assert _settings(embedding_dimensions=1536).embedding_dimensions == 1536
    with pytest.raises(ValidationError):
        _settings(embedding_dimensions=100)


def test_public_demo_blocks_groq(monkeypatch) -> None:
    from app.core.errors import AppError
    from app.integrations.language import get_chat_client

    demo = get_settings().model_copy(update={"public_demo": True, "llm_provider": "groq"})
    monkeypatch.setattr("app.integrations.language.get_settings", lambda: demo)
    with pytest.raises(AppError) as caught:
        get_chat_client()
    assert caught.value.code == "llm_unconfigured"
    with pytest.raises(ValidationError):
        _settings(public_demo=True, llm_provider="groq", llm_api_key="gsk-test")


def test_production_rejects_deterministic_providers() -> None:
    with pytest.raises(ValidationError):
        _settings(
            environment="production",
            secret_key="a-real-production-secret-key-value",
            cookie_secure=True,
            llm_provider="double",
        )


def test_secure_cookie_flag_follows_configuration() -> None:
    settings = get_settings().model_copy(update={"cookie_secure": True})
    response = Response()
    attach_session_cookie(response, settings, uuid.uuid4())
    header = response.headers["set-cookie"].lower()
    assert "secure" in header
    assert "httponly" in header
    assert "samesite=lax" in header
