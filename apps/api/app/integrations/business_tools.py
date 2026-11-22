import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.errors import AppError
from app.domains.crm import service as crm
from app.domains.crm.models import Lead
from app.domains.knowledge.retrieval import search_chunks
from app.integrations.language import get_embedding_client

# The process environment fixes the organization. Tool arguments cannot select another one.


def build_server(organization_id: uuid.UUID) -> MCPServer:
    server = MCPServer("atlas-business")

    @server.tool(structured_output=False)
    def find_contact(name: str) -> str:
        """Find a contact in the server's organization. Read only."""

        _bounded(name, 200)
        with _session() as db:
            return json.dumps(_find_contact(db, organization_id, name.strip()))

    @server.tool(structured_output=False)
    def get_lead(lead_id: str) -> str:
        """Read one lead in the server's organization."""

        _bounded(lead_id, 80)
        try:
            parsed = uuid.UUID(lead_id)
        except ValueError as exc:
            raise ToolError("Resource not found") from exc
        with _session() as db:
            try:
                lead = crm.get_lead(db, organization_id, parsed)
            except AppError as exc:
                raise ToolError("Resource not found") from exc
            return json.dumps(_lead_payload(lead))

    @server.tool(structured_output=False)
    def search_company_knowledge(query: str) -> str:
        """Search ready company documents for the server's organization. Read only."""

        _bounded(query, 2000)
        with _session() as db:
            try:
                hits = search_chunks(db, organization_id, query, get_embedding_client(), limit=5)
            except AppError as exc:
                raise ToolError(exc.message) from exc
        return json.dumps(
            [
                {
                    "document_id": str(hit.document_id),
                    "chunk_id": str(hit.chunk_id),
                    "document_title": hit.document_title,
                    "content": hit.content[:500],
                    "score": hit.score,
                }
                for hit in hits
            ]
        )

    return server


def _bounded(value: str, limit: int) -> None:
    if len(value) > limit:
        raise ToolError("The tool arguments are not valid")


def _find_contact(db: Session, organization_id: uuid.UUID, name: str) -> dict[str, Any] | None:
    if len(name) < 2:
        return None
    contacts, _ = crm.list_contacts(
        db, organization_id, q=name, company_id=None, page=1, page_size=5
    )
    if not contacts:
        return None
    needle = name.casefold()
    contact = next((item for item in contacts if item.full_name.casefold() == needle), contacts[0])
    lead = db.scalar(
        select(Lead)
        .where(Lead.organization_id == organization_id, Lead.contact_id == contact.id)
        .order_by(Lead.updated_at.desc())
    )
    return {
        "id": str(contact.id),
        "full_name": contact.full_name,
        "email": contact.email,
        "company_id": str(contact.company_id) if contact.company_id else None,
        "lead_id": str(lead.id) if lead is not None else None,
    }


def _lead_payload(lead: Lead) -> dict[str, Any]:
    status = lead.status.value if hasattr(lead.status, "value") else str(lead.status)
    return {
        "id": str(lead.id),
        "title": lead.title,
        "status": status,
        "company_id": str(lead.company_id) if lead.company_id else None,
        "contact_id": str(lead.contact_id) if lead.contact_id else None,
        "notes": lead.notes,
    }


@contextmanager
def _session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
