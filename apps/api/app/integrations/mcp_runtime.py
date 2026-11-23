"""Choose and check the Python process that serves MCP tools.

Windows can launch the API with the base interpreter while the project packages
live in the virtualenv. MCP children must use that virtualenv, not ``sys.executable``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import structlog

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.integrations.resolver import resolve_settings

logger = structlog.get_logger(__name__)

McpCategory = Literal["ready", "import_failure", "tool_failure", "timeout", "crash", "missing"]

_API_ROOT = Path(__file__).resolve().parents[2]
_READY_STATEMENT = (
    "import uuid; import mcp; "
    "from app.integrations.business_tools import build_server; "
    "build_server(uuid.uuid4())"
)
_INHERITED = (
    "APPDATA",
    "HOMEDRIVE",
    "HOMEPATH",
    "LOCALAPPDATA",
    "PATH",
    "PATHEXT",
    "PROCESSOR_ARCHITECTURE",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "USERNAME",
    "USERPROFILE",
    "HOME",
    "LANG",
    "LC_ALL",
)
_EXCEPTION_TYPE = re.compile(
    r"(?m)^(?:[A-Za-z_][\w.]*\.)?([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\b"
)
_SECRET_TEXT = re.compile(
    r"gsk_|postgresql(?:\+psycopg)?://|Bearer\s|ATLAS_SECRET|ATLAS_DATABASE|api_key",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class McpProcessStatus:
    executable: str
    category: McpCategory
    exit_code: int | None
    exception_type: str | None


def venv_python(root: Path) -> Path:
    scripts = "Scripts" if os.name == "nt" else "bin"
    name = "python.exe" if os.name == "nt" else "python"
    return root / scripts / name


def resolve_mcp_python(
    *,
    configured: str | None = None,
    executable: str = sys.executable,
    prefix: str = sys.prefix,
    base_prefix: str = sys.base_prefix,
    virtual_env: str | None = None,
) -> str:
    """Return the interpreter that should run ``python -m app.mcp_server``."""

    if configured is None:
        configured = get_settings().mcp_python
    selected = configured.strip()
    if selected:
        if not Path(selected).is_file():
            raise ValueError("ATLAS_MCP_PYTHON must be an existing executable")
        return selected
    if prefix != base_prefix:
        candidate = venv_python(Path(prefix))
        if candidate.is_file():
            return str(candidate)
    env_root = virtual_env if virtual_env is not None else os.environ.get("VIRTUAL_ENV")
    if env_root:
        candidate = venv_python(Path(env_root))
        if candidate.is_file():
            return str(candidate)
    return executable


def virtualenv_root(executable: str) -> str | None:
    path = Path(executable).resolve()
    root = path.parent.parent
    if path.parent.name not in {"Scripts", "bin"} or not (root / "pyvenv.cfg").is_file():
        return None
    return str(root)


def mcp_process_env(*, organization_id: str | None = None) -> dict[str, str]:
    """Environment for an MCP child. The chat key is not included."""

    settings = get_settings()
    if organization_id is not None:
        db = SessionLocal()
        try:
            settings = resolve_settings(db, uuid.UUID(organization_id), "embedding")
        finally:
            db.close()
    env = _process_env()
    env.update(
        {
            "ATLAS_DATABASE_URL": _configured("ATLAS_DATABASE_URL", settings.database_url),
            "ATLAS_SECRET_KEY": _configured("ATLAS_SECRET_KEY", settings.secret_key),
            "ATLAS_ENVIRONMENT": _configured("ATLAS_ENVIRONMENT", settings.environment),
            "ATLAS_COOKIE_SECURE": _configured(
                "ATLAS_COOKIE_SECURE", "true" if settings.cookie_secure else "false"
            ),
            "ATLAS_EMAIL_MODE": _configured("ATLAS_EMAIL_MODE", settings.email_mode),
            "ATLAS_EMAIL_LIVE_ENABLED": _configured(
                "ATLAS_EMAIL_LIVE_ENABLED", "true" if settings.email_live_enabled else "false"
            ),
            "ATLAS_SMTP_HOST": _configured("ATLAS_SMTP_HOST", settings.smtp_host),
            "ATLAS_EMBEDDING_PROVIDER": _configured(
                "ATLAS_EMBEDDING_PROVIDER", settings.embedding_provider
            ),
            "ATLAS_LLM_PROVIDER": _configured("ATLAS_LLM_PROVIDER", settings.llm_provider),
            "ATLAS_LLM_BASE_URL": _configured("ATLAS_LLM_BASE_URL", settings.llm_base_url),
            "ATLAS_LLM_MODEL": _configured("ATLAS_LLM_MODEL", settings.llm_model),
            "ATLAS_PUBLIC_DEMO": _configured(
                "ATLAS_PUBLIC_DEMO", "true" if settings.public_demo else "false"
            ),
            "ATLAS_EMBEDDING_API_KEY": _configured(
                "ATLAS_EMBEDDING_API_KEY", settings.embedding_api_key
            ),
            "ATLAS_EMBEDDING_BASE_URL": _configured(
                "ATLAS_EMBEDDING_BASE_URL", settings.embedding_base_url
            ),
            "ATLAS_EMBEDDING_MODEL": _configured("ATLAS_EMBEDDING_MODEL", settings.embedding_model),
            "ATLAS_EMBEDDING_DIMENSIONS": _configured(
                "ATLAS_EMBEDDING_DIMENSIONS", str(settings.embedding_dimensions)
            ),
            "ATLAS_MAX_COSINE_DISTANCE": _configured(
                "ATLAS_MAX_COSINE_DISTANCE", str(settings.max_cosine_distance)
            ),
            "ATLAS_LOG_LEVEL": "WARNING",
        }
    )
    if organization_id is not None:
        env["ATLAS_MCP_ORGANIZATION_ID"] = organization_id
    return env


def probe_mcp_interpreter(
    executable: str | None = None, *, statement: str = _READY_STATEMENT
) -> McpProcessStatus:
    selected = executable or resolve_mcp_python()
    if not Path(selected).is_file():
        return McpProcessStatus(selected, "missing", None, None)
    env = mcp_process_env()
    root = virtualenv_root(selected)
    if root is not None:
        env["VIRTUAL_ENV"] = root
    try:
        result = subprocess.run(
            [selected, "-c", statement],
            cwd=_API_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return McpProcessStatus(selected, "timeout", None, None)
    except OSError:
        return McpProcessStatus(selected, "crash", None, None)
    return _status_from_process(selected, result.returncode, result.stderr)


def require_mcp_interpreter() -> McpProcessStatus:
    """Stop startup when the tool interpreter cannot import the MCP package.

    Tests boot the app many times and use their own interpreter, so they skip this probe.
    """

    settings = get_settings()
    if settings.environment == "test":
        selected = resolve_mcp_python()
        return McpProcessStatus(selected, "ready", None, None)
    status = probe_mcp_interpreter()
    log_mcp_status(status)
    if status.category != "ready":
        raise RuntimeError("The MCP interpreter cannot import its dependencies")
    return status


def classify_tool_failure(
    stderr: str, *, timed_out: bool = False, tool_error: bool = False
) -> McpCategory:
    if timed_out:
        return "timeout"
    if _exception_type(stderr) in {"ModuleNotFoundError", "ImportError"}:
        return "import_failure"
    if tool_error or "Error executing tool" in stderr:
        return "tool_failure"
    return "crash"


def public_tool_message(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned or _SECRET_TEXT.search(cleaned):
        return "The business tool failed"
    return cleaned[:200]


def observed_status(
    executable: str, stderr: str, *, timed_out: bool = False, tool_error: bool = False
) -> McpProcessStatus:
    return McpProcessStatus(
        executable,
        classify_tool_failure(stderr, timed_out=timed_out, tool_error=tool_error),
        None,
        _exception_type(stderr),
    )


def log_mcp_status(status: McpProcessStatus, *, tool: str | None = None) -> None:
    logger.info(
        "mcp_process",
        tool=tool,
        executable=status.executable,
        category=status.category,
        exit_code=status.exit_code,
        exception_type=status.exception_type,
    )


def _process_env() -> dict[str, str]:
    return {key: os.environ[key] for key in _INHERITED if key in os.environ}


def _configured(name: str, fallback: str) -> str:
    return os.environ.get(name, fallback)


def _exception_type(stderr: str) -> str | None:
    found = _EXCEPTION_TYPE.findall(stderr)
    if not found:
        return None
    name = found[-1]
    if not isinstance(name, str):
        return None
    return name[:80]


def _status_from_process(executable: str, exit_code: int, stderr: str) -> McpProcessStatus:
    exception_type = _exception_type(stderr)
    if exit_code == 0:
        return McpProcessStatus(executable, "ready", exit_code, exception_type)
    if exception_type in {"ModuleNotFoundError", "ImportError"}:
        category: McpCategory = "import_failure"
    else:
        category = "crash"
    return McpProcessStatus(executable, category, exit_code, exception_type)
