import asyncio
import json
import uuid

from mcp import Client
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.crm.models import Lead, LeadStatus
from app.domains.crm.service import create_company, create_contact, create_lead
from app.domains.identity.models import MembershipRole
from app.integrations.business_mcp import server_parameters
from tests.factories import make_membership, make_organization, make_user


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
        "find_contact",
        "get_lead",
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


def _titles(db: Session, organization_id: uuid.UUID) -> list[str]:
    return list(db.scalars(select(Lead.title).where(Lead.organization_id == organization_id)).all())
