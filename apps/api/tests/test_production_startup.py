import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.main import create_app
from tests.bootstrap import API_ROOT, TEST_DATABASE_URL


def test_public_demo_hides_the_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings().model_copy(
        update={
            "public_demo": True,
            "llm_api_key": "",
            "embedding_api_key": "",
            "n8n_lead_webhook_url": "",
            "email_mode": "sandbox",
            "email_live_enabled": False,
        }
    )
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    app = create_app()
    assert app.docs_url is None
    assert app.openapi_url is None


def test_production_startup_has_a_secure_session_and_no_demo_seed(tmp_path: Path) -> None:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("ATLAS_")}
    environment.update(
        {
            "ATLAS_MCP_ISOLATED_SETTINGS": "1",
            "ATLAS_ENVIRONMENT": "production",
            "ATLAS_SECRET_KEY": secrets.token_hex(32),
            "ATLAS_CREDENTIAL_ENCRYPTION_KEYS": f"qualification={secrets.token_hex(32)}",
            "ATLAS_DATABASE_URL": TEST_DATABASE_URL,
            "ATLAS_COOKIE_SECURE": "true",
            "ATLAS_CORS_ORIGINS": "https://atlas.example.com",
            "ATLAS_STORAGE_DIR": str(tmp_path / "storage"),
            "ATLAS_MODEL_DIR": str(tmp_path / "models"),
        }
    )
    proof = """
import json
import secrets

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import create_app
from app.scripts.bootstrap import main, status_line

with SessionLocal() as db:
    assert status_line(db) == (
        "bootstrap_status users=0 organizations=0 administrators=0 companies=0"
    )

credentials = {"email": "qualification@example.com", "password": secrets.token_hex(24)}
bootstrap = {
    **credentials,
    "organization_name": "Qualification Workspace",
    "organization_slug": "qualification-workspace",
    "full_name": "Release Administrator",
}
assert main(stdin_text=json.dumps(bootstrap)) == 0
assert main(stdin_text=json.dumps(bootstrap)) == 2
with TestClient(create_app(), base_url="https://atlas.example.com") as client:
    assert client.get("/api/v1/ready").json() == {"status": "ok", "database": "ok"}
    assert client.get("/docs").status_code == 404
    result = client.post("/api/v1/auth/login", json=credentials)
    assert result.status_code == 200
    cookie = result.headers["set-cookie"].lower()
    assert all(attribute in cookie for attribute in ("httponly", "secure", "samesite=lax"))
    session = client.get("/api/v1/auth/me")
    assert session.status_code == 200
    assert session.json()["memberships"][0]["role"] == "admin"
    assert client.post("/api/v1/auth/logout").status_code == 403
with SessionLocal() as db:
    assert status_line(db) == (
        "bootstrap_status users=1 organizations=1 administrators=1 companies=0"
    )
"""
    completed = subprocess.run(
        [sys.executable, "-c", proof],
        cwd=API_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
