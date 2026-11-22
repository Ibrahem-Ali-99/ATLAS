import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers


def test_unhandled_error_hides_exception_text() -> None:
    app = FastAPI()
    register_exception_handlers(app)
    marker = "db-url-should-not-be-logged"

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError(marker)

    with structlog.testing.capture_logs() as logs:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/boom")

    rendered = repr(logs)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert marker not in response.text
    assert marker not in rendered
    assert any(entry["event"] == "unhandled_error" for entry in logs)
    assert any(entry["error_type"] == "RuntimeError" for entry in logs)
