import asyncio
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.integrations.mcp_runtime import (
    log_mcp_status,
    mcp_process_env,
    observed_status,
    public_tool_message,
    resolve_mcp_python,
    virtualenv_root,
)

ALLOWED_TOOLS = frozenset({"find_contact", "get_lead", "search_company_knowledge"})


class BusinessToolError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class TransientToolError(BusinessToolError):
    """A tool call that may succeed if the same read is attempted again."""


def server_parameters(organization_id: uuid.UUID) -> StdioServerParameters:
    api_root = Path(__file__).resolve().parents[2]
    env = mcp_process_env(organization_id=str(organization_id))
    command = resolve_mcp_python()
    root = virtualenv_root(command)
    if root is not None:
        env["VIRTUAL_ENV"] = root
    return StdioServerParameters(
        command=command,
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
    parameters = server_parameters(organization_id)
    descriptor, raw_path = tempfile.mkstemp(prefix="atlas-mcp-")
    os.close(descriptor)
    captured = Path(raw_path)
    try:
        try:
            with captured.open("w", encoding="utf-8", errors="replace") as errlog:
                async with Client(
                    stdio_client(parameters, errlog=errlog),
                    mode="legacy",
                    read_timeout_seconds=30.0,
                ) as client:
                    result = await client.call_tool(name, arguments)
        except BusinessToolError:
            raise
        except (TimeoutError, OSError, ConnectionError) as exc:
            _log_capture(
                parameters.command,
                name,
                captured,
                timed_out=isinstance(exc, TimeoutError),
            )
            raise
        except Exception as exc:
            _log_capture(parameters.command, name, captured)
            raise BusinessToolError("The business tool failed") from exc
        else:
            if result.is_error:
                _log_capture(parameters.command, name, captured, tool_error=True)
                message = public_tool_message(_text(result)) or "The business tool failed"
                raise BusinessToolError(message)
    finally:
        captured.unlink(missing_ok=True)
    try:
        return json.loads(_text(result))
    except json.JSONDecodeError as exc:
        raise BusinessToolError("The business tool returned an unexpected response") from exc


def _log_capture(
    executable: str,
    tool: str,
    captured: Path,
    *,
    timed_out: bool = False,
    tool_error: bool = False,
) -> None:
    stderr = captured.read_text(encoding="utf-8", errors="replace") if captured.is_file() else ""
    log_mcp_status(
        observed_status(executable, stderr, timed_out=timed_out, tool_error=tool_error),
        tool=tool,
    )


def _text(result: Any) -> str:
    parts: list[str] = []
    for block in result.content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _trace_tool(organization_id: uuid.UUID, name: str, status: str) -> None:
    from app.domains.observability.tracing import record_operation

    record_operation(
        operation="mcp_tool",
        status=status,
        organization_id=organization_id,
        detail={"tool": name},
    )
