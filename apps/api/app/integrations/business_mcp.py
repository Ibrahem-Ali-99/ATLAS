import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from app.core.config import get_settings

ALLOWED_TOOLS = frozenset({"find_contact", "get_lead", "search_company_knowledge"})


class BusinessToolError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class TransientToolError(BusinessToolError):
    """A tool call that may succeed if the same read is attempted again."""


def server_parameters(organization_id: uuid.UUID) -> StdioServerParameters:
    settings = get_settings()
    api_root = Path(__file__).resolve().parents[2]
    env = {
        "ATLAS_MCP_ORGANIZATION_ID": str(organization_id),
        "ATLAS_DATABASE_URL": _env("ATLAS_DATABASE_URL", settings.database_url),
        "ATLAS_SECRET_KEY": _env("ATLAS_SECRET_KEY", settings.secret_key),
        "ATLAS_ENVIRONMENT": _env("ATLAS_ENVIRONMENT", settings.environment),
        "ATLAS_EMBEDDING_API_KEY": _env("ATLAS_EMBEDDING_API_KEY", settings.embedding_api_key),
        "ATLAS_EMBEDDING_BASE_URL": _env("ATLAS_EMBEDDING_BASE_URL", settings.embedding_base_url),
        "ATLAS_EMBEDDING_MODEL": _env("ATLAS_EMBEDDING_MODEL", settings.embedding_model),
        "ATLAS_EMBEDDING_DIMENSIONS": _env(
            "ATLAS_EMBEDDING_DIMENSIONS", str(settings.embedding_dimensions)
        ),
        "ATLAS_MAX_COSINE_DISTANCE": _env(
            "ATLAS_MAX_COSINE_DISTANCE", str(settings.max_cosine_distance)
        ),
        "ATLAS_LOG_LEVEL": "WARNING",
    }
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"],
        cwd=api_root,
        env=env,
    )


class BusinessTools:
    """MCP client for the read-only tools. The organization is fixed on the server."""

    def __init__(self, organization_id: uuid.UUID) -> None:
        self.organization_id = organization_id

    def find_contact(self, name: str) -> dict[str, Any] | None:
        found = call_tool(self.organization_id, "find_contact", {"name": name})
        if found is None:
            return None
        if not isinstance(found, dict):
            raise BusinessToolError("The business tool returned an unexpected response")
        return found

    def get_lead(self, lead_id: str) -> dict[str, Any]:
        lead = call_tool(self.organization_id, "get_lead", {"lead_id": lead_id})
        if not isinstance(lead, dict):
            raise BusinessToolError("The business tool returned an unexpected response")
        return lead

    def search_company_knowledge(self, query: str) -> list[dict[str, Any]]:
        hits = call_tool(self.organization_id, "search_company_knowledge", {"query": query})
        if not isinstance(hits, list):
            raise BusinessToolError("The business tool returned an unexpected response")
        return [hit for hit in hits if isinstance(hit, dict)]


def call_tool(organization_id: uuid.UUID, name: str, arguments: dict[str, Any]) -> Any:
    if name not in ALLOWED_TOOLS:
        raise BusinessToolError("This tool is not available to the agent")
    try:
        result = asyncio.run(_call(organization_id, name, arguments))
    except BusinessToolError:
        _trace_tool(organization_id, name, "failed")
        raise
    except (TimeoutError, OSError, ConnectionError) as exc:
        _trace_tool(organization_id, name, "failed")
        raise TransientToolError("The business tool is unavailable") from exc
    _trace_tool(organization_id, name, "succeeded")
    return result


async def _call(organization_id: uuid.UUID, name: str, arguments: dict[str, Any]) -> Any:
    try:
        async with Client(
            server_parameters(organization_id), mode="legacy", read_timeout_seconds=30.0
        ) as client:
            result = await client.call_tool(name, arguments)
    except BusinessToolError:
        raise
    except Exception as exc:
        raise BusinessToolError("The business tool failed") from exc
    if result.is_error:
        raise BusinessToolError(_text(result)[:200] or "The business tool failed")
    try:
        return json.loads(_text(result))
    except json.JSONDecodeError as exc:
        raise BusinessToolError("The business tool returned an unexpected response") from exc


def _text(result: Any) -> str:
    parts: list[str] = []
    for block in result.content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _env(name: str, fallback: str) -> str:
    return os.environ.get(name, fallback)


def _trace_tool(organization_id: uuid.UUID, name: str, status: str) -> None:
    from app.domains.observability.tracing import record_operation

    record_operation(
        operation="mcp_tool",
        status=status,
        organization_id=organization_id,
        detail={"tool": name},
    )
