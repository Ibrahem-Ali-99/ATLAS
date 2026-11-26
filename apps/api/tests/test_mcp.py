import asyncio
import json
import sys
import uuid
from pathlib import Path

import pytest
from mcp import Client
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domains.crm.models import Lead, LeadStatus
from app.domains.crm.service import create_company, create_contact, create_lead
from app.domains.identity.models import MembershipRole
from app.integrations.business_mcp import server_parameters
from app.integrations.mcp_runtime import (
    mcp_process_env,
    probe_mcp_interpreter,
    public_tool_message,
    resolve_mcp_python,
    venv_python,
)
from tests.factories import make_membership, make_organization, make_user


def test_mcp_child_receives_the_embedding_provider(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_EMBEDDING_PROVIDER", "double")
    env = server_parameters(uuid.uuid4()).env
    assert env is not None
    assert env["ATLAS_EMBEDDING_PROVIDER"] == "double"
    assert env["ATLAS_LLM_MODEL"]
    assert env["ATLAS_PUBLIC_DEMO"] == "false"
    assert "ATLAS_LLM_API_KEY" not in env
    assert env["ATLAS_MCP_ORGANIZATION_ID"]
    assert server_parameters(uuid.uuid4()).command == resolve_mcp_python()


def test_mcp_child_env_keeps_production_cookie_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ENVIRONMENT", "production")
    monkeypatch.setenv("ATLAS_COOKIE_SECURE", "true")
    monkeypatch.setenv("ATLAS_SECRET_KEY", "a-real-production-secret-key-value")
    monkeypatch.setenv("ATLAS_EMAIL_MODE", "sandbox")
    monkeypatch.setenv("ATLAS_SMTP_HOST", "mailpit")
    env = mcp_process_env()
    settings = Settings(
        _env_file=None,
        environment=env["ATLAS_ENVIRONMENT"],
        secret_key=env["ATLAS_SECRET_KEY"],
        credential_encryption_keys=env["ATLAS_CREDENTIAL_ENCRYPTION_KEYS"],
        database_url=env["ATLAS_DATABASE_URL"],
        cookie_secure=env["ATLAS_COOKIE_SECURE"] == "true",
        email_mode=env["ATLAS_EMAIL_MODE"],
        smtp_host=env["ATLAS_SMTP_HOST"],
        email_live_enabled=env["ATLAS_EMAIL_LIVE_ENABLED"] == "true",
        llm_provider=env["ATLAS_LLM_PROVIDER"],
        embedding_provider=env["ATLAS_EMBEDDING_PROVIDER"],
        public_demo=env["ATLAS_PUBLIC_DEMO"] == "true",
        embedding_dimensions=int(env["ATLAS_EMBEDDING_DIMENSIONS"]),
    )
    assert settings.environment == "production"
    assert settings.cookie_secure is True


def test_mcp_stdio_session_is_read_only_and_organization_scoped(db: Session) -> None:
    """Uses a stdio MCP client and server. This is not a direct Python call."""

    owner = make_user(db, "olivia@example.org")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    northwind = make_organization(db, "Northwind", "northwind")
    make_membership(db, owner, northwind, MembershipRole.admin)
    harbor = create_company(db, atlas.id, {"name": "Harbor"})
    other = create_company(db, northwind.id, {"name": "Other"})
    create_contact(
        db,
        atlas.id,
        {"full_name": "Mina Patel", "email": "mina@harbor.example", "company_id": harbor.id},
    )
    create_contact(
        db,
        northwind.id,
        {"full_name": "Mina Patel", "email": "mina@northwind.example", "company_id": other.id},
    )
    secret = create_lead(
        db,
        northwind.id,
        owner.id,
        {"title": "Northwind secret", "status": LeadStatus.new, "company_id": other.id},
    )
    before = _titles(db, atlas.id)

    listed, found, denied, hidden = asyncio.run(_session(atlas.id, secret.id))

    assert {tool["name"] for tool in listed} == {
        "calendar_availability",
        "find_contact",
        "get_lead",
        "message_delivery",
        "provider_health",
        "search_company_knowledge",
    }
    for tool in listed:
        properties = tool["properties"]
        assert isinstance(properties, list)
        assert "organization_id" not in properties
    assert found["email"] == "mina@harbor.example"
    assert "mina@northwind.example" not in json.dumps(found)
    assert denied is True
    assert hidden is True
    assert _titles(db, atlas.id) == before


async def _session(
    organization_id: uuid.UUID, secret_lead_id: uuid.UUID
) -> tuple[list[dict[str, object]], dict[str, object], bool, bool]:
    async with Client(server_parameters(organization_id), mode="legacy") as client:
        listed_result = await client.list_tools()
        listed: list[dict[str, object]] = [
            {"name": tool.name, "properties": list(tool.input_schema.get("properties", {}))}
            for tool in listed_result.tools
        ]
        found_result = await client.call_tool("find_contact", {"name": "Mina Patel"})
        found = json.loads(_text(found_result))
        assert isinstance(found, dict)
        try:
            denied_result = await client.call_tool("create_lead", {"title": "nope"})
        except Exception:
            denied = True
        else:
            denied = bool(denied_result.is_error)
        hidden_result = await client.call_tool("get_lead", {"lead_id": str(secret_lead_id)})
        hidden = bool(hidden_result.is_error) or "Northwind secret" not in _text(hidden_result)
    return listed, found, denied, hidden


def _text(result: object) -> str:
    parts: list[str] = []
    for block in getattr(result, "content", []):
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def test_selected_interpreter_loads_the_mcp_server() -> None:
    status = probe_mcp_interpreter()
    assert status.category == "ready"
    assert status.exit_code == 0
    assert Path(status.executable).is_file()
    assert server_parameters(uuid.uuid4()).command == status.executable


def test_missing_import_is_classified_without_the_stderr_body() -> None:
    status = probe_mcp_interpreter(sys.executable, statement="import atlas_mcp_dependency_missing")
    assert status.category == "import_failure"
    assert status.exit_code == 1
    assert status.exception_type == "ModuleNotFoundError"


def test_resolver_uses_the_virtualenv_when_the_process_image_is_the_base(tmp_path: Path) -> None:
    candidate = venv_python(tmp_path)
    candidate.parent.mkdir()
    candidate.write_bytes(b"")
    selected = resolve_mcp_python(
        configured="",
        executable=str(tmp_path / "base-python"),
        prefix=str(tmp_path),
        base_prefix=str(tmp_path / "base"),
        virtual_env=None,
    )
    assert selected == str(candidate)


def test_configured_interpreter_must_exist(tmp_path: Path) -> None:
    missing = tmp_path / "missing-python"
    with pytest.raises(ValueError, match="ATLAS_MCP_PYTHON"):
        resolve_mcp_python(configured=str(missing))
    with pytest.raises(ValidationError):
        Settings(
            secret_key="test-secret-key-must-be-32-chars-min",
            database_url="postgresql+psycopg://atlas:atlas@localhost/atlas",
            mcp_python=str(missing),
        )


def test_public_tool_message_drops_secret_text() -> None:
    assert public_tool_message("Error executing tool search_company_knowledge") == (
        "Error executing tool search_company_knowledge"
    )
    assert public_tool_message("postgresql+psycopg://atlas:atlas@localhost/atlas") == (
        "The business tool failed"
    )


def _titles(db: Session, organization_id: uuid.UUID) -> list[str]:
    return list(db.scalars(select(Lead.title).where(Lead.organization_id == organization_id)).all())
