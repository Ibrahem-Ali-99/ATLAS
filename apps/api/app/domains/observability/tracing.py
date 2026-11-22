"""Record an operation without customer content or credentials."""

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domains.observability.models import OperationTrace

logger = structlog.get_logger(__name__)

_SECRET_KEYS = {
    "authorization",
    "cookie",
    "secret",
    "password",
    "api_key",
    "x-atlas-signature",
    "x-atlas-key-id",
    "set-cookie",
}


def estimate_cost(tokens_in: int | None, tokens_out: int | None) -> float | None:
    settings = get_settings()
    if tokens_in is None or tokens_out is None:
        return None
    if settings.llm_input_usd_per_million is None or settings.llm_output_usd_per_million is None:
        return None
    return round(
        (tokens_in / 1_000_000) * settings.llm_input_usd_per_million
        + (tokens_out / 1_000_000) * settings.llm_output_usd_per_million,
        8,
    )


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in _SECRET_KEYS or "token" in str(key).lower():
                cleaned[str(key)] = "[redacted]"
            else:
                cleaned[str(key)] = redact(item)
        return cleaned
    if isinstance(value, list):
        return [redact(item) for item in value[:20]]
    if isinstance(value, str) and len(value) > 120:
        return value[:120]
    return value


def record_operation(
    *,
    operation: str,
    status: str,
    organization_id: uuid.UUID | None = None,
    inquiry_id: uuid.UUID | None = None,
    agent_run_id: uuid.UUID | None = None,
    approval_id: uuid.UUID | None = None,
    workflow_run_id: uuid.UUID | None = None,
    latency_ms: int | None = None,
    provider: str | None = None,
    model_name: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    error_code: str | None = None,
    attempt: int = 1,
    detail: dict[str, Any] | None = None,
) -> None:
    safe_detail = redact(detail or {})
    if not isinstance(safe_detail, dict):
        safe_detail = {}
    cost = estimate_cost(tokens_in, tokens_out)
    payload = {
        "operation": operation,
        "status": status,
        "organization_id": None if organization_id is None else str(organization_id),
        "inquiry_id": None if inquiry_id is None else str(inquiry_id),
        "agent_run_id": None if agent_run_id is None else str(agent_run_id),
        "approval_id": None if approval_id is None else str(approval_id),
        "workflow_run_id": None if workflow_run_id is None else str(workflow_run_id),
        "latency_ms": latency_ms,
        "provider": provider,
        "model_name": model_name,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost,
        "error_code": error_code,
        "attempt": attempt,
    }
    try:
        langfuse_status = export_langfuse(payload)
    except Exception:
        logger.error("langfuse_unavailable", operation=operation)
        langfuse_status = "unavailable"
    try:
        with SessionLocal() as db:
            db.add(
                OperationTrace(
                    organization_id=organization_id,
                    inquiry_id=inquiry_id,
                    agent_run_id=agent_run_id,
                    approval_id=approval_id,
                    workflow_run_id=workflow_run_id,
                    operation=operation,
                    status=status,
                    finished_at=datetime.now(UTC),
                    latency_ms=latency_ms,
                    provider=provider,
                    model_name=model_name,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost,
                    error_code=error_code,
                    attempt=attempt,
                    langfuse_status=langfuse_status,
                    detail=safe_detail,
                )
            )
            db.commit()
    except Exception:
        logger.error("trace_record_failed", operation=operation)


def export_langfuse(payload: dict[str, Any]) -> str:
    settings = get_settings()
    if not settings.langfuse_public_key.strip() or not settings.langfuse_secret_key.strip():
        return "unconfigured"
    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host or None,
        )
        metadata = {key: value for key, value in payload.items() if value is not None}
        event = getattr(client, "create_event", None)
        if not callable(event):
            return "unavailable"
        created = event(name=str(payload["operation"]), metadata=metadata)
        end = getattr(created, "end", None)
        if callable(end):
            end()
        flush = getattr(client, "flush", None)
        if callable(flush):
            flush()
        return "sent"
    except Exception:
        logger.error("langfuse_unavailable", operation=str(payload.get("operation")))
        return "unavailable"
