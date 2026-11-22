import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.database import get_db
from app.main import create_app


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "atlas-api"}
    assert response.headers["x-request-id"]


def test_ready(client: TestClient) -> None:
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_ready_when_database_is_unavailable() -> None:
    class BrokenSession:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise OperationalError("SELECT 1", {}, Exception("database down"))

        def close(self) -> None:
            return None

    def override() -> object:
        yield BrokenSession()

    application = create_app()
    application.dependency_overrides[get_db] = override
    with TestClient(application) as test_client:
        response = test_client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "not_ready"


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_validation_error_omits_submitted_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": "x7"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "x7" not in response.text


@pytest.mark.parametrize("origin", ["http://127.0.0.1:3000", "http://localhost:3000"])
def test_cors_allows_configured_origin(client: TestClient, origin: str) -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_does_not_reflect_unknown_origin(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "http://evil.example"})
    assert response.headers.get("access-control-allow-origin") is None
