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
