import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.agents.models import AgentEvent, AgentRun, RunStatus
from app.domains.approvals.models import Approval, ApprovalStatus
from app.domains.automation.models import (
    CalendarBooking,
    EmailMessage,
    EmailStatus,
    ExecutionAttempt,
    WorkflowRun,
    WorkflowStatus,
)
from app.domains.crm.models import Inquiry
from app.domains.integrations.calendar_models import GoogleCalendarConnection
from app.domains.integrations.models import IntegrationConfig
from app.domains.knowledge.models import Document, DocumentStatus, IngestionJob, IngestionJobStatus
from app.domains.observability.models import OperationTrace, WorkerHeartbeat
from app.domains.provenance.origin import DataScope, scope_clause

_HINTS = {
    "callback_missing": "n8n acknowledged the lead event and no matching callback is stored.",
    "execution_uncertain": "The worker stopped before the external result was stored.",
    "llm_unconfigured": "The language model key is empty, so the run was stored as failed.",
    "interrupted": "The API restarted while this run was still marked running.",
    "n8n_timeout": "The n8n call timed out and was not sent again.",
    "smtp_timeout": "The SMTP result was uncertain and the message was not sent again.",
}


_FRESH_SECONDS = 45
_RECENT = timedelta(hours=24)
_ACTIVITY_NOTICE = (
    "Current health is the latest stored state. Incidents are earlier records "
    "and are not still running."
)


def diagnostics(
    db: Session,
    organization_id: uuid.UUID,
    scope: DataScope = DataScope.operational,
    *,
    include_platform: bool = True,
) -> dict[str, Any]:
    traces = list(
        db.scalars(
            select(OperationTrace)
            .where(OperationTrace.organization_id == organization_id)
            .order_by(OperationTrace.latency_ms.desc().nulls_last())
            .limit(50)
        )
    )
    failed_runs = list(
        db.scalars(
            select(AgentRun)
            .where(*_scoped(AgentRun, organization_id, scope), AgentRun.status == RunStatus.failed)
            .order_by(AgentRun.started_at.desc())
            .limit(20)
        )
    )
    attention = list(
        db.scalars(
            select(Approval)
            .where(
                *_scoped(Approval, organization_id, scope),
                Approval.status == ApprovalStatus.needs_attention,
            )
            .limit(20)
        )
    )
    workflow_failures = list(
        db.scalars(
            select(WorkflowRun)
            .where(
                *_scoped(WorkflowRun, organization_id, scope),
                WorkflowRun.status.in_([WorkflowStatus.failed, WorkflowStatus.needs_attention]),
            )
            .order_by(WorkflowRun.created_at.desc())
            .limit(20)
        )
    )
    retries = int(
        db.scalar(
            select(func.count())
            .select_from(ExecutionAttempt)
            .where(
                *_scoped(ExecutionAttempt, organization_id, scope),
                ExecutionAttempt.outcome.in_(("failed", "uncertain")),
            )
        )
        or 0
    )
    costs = [trace.cost_usd for trace in traces if trace.cost_usd is not None]
    now = datetime.now(UTC)
    workers = (
        list(db.scalars(select(WorkerHeartbeat).order_by(WorkerHeartbeat.worker_kind)))
        if include_platform
        else []
    )
    ingestion = list(
        db.scalars(
            select(IngestionJob)
            .where(IngestionJob.organization_id == organization_id)
            .order_by(IngestionJob.updated_at.desc())
            .limit(50)
        )
    )
    return {
        "scope": scope.value,
        "hint_notice": "Hints name a recorded error code. They are not a root-cause finding.",
        "failed_runs": [
            {"id": run.id, "error_code": run.error_code, "hint": _HINTS.get(run.error_code or "")}
            for run in failed_runs
        ],
        "slowest_steps": []
        if not include_platform
        else [
            {
                "operation": trace.operation,
                "latency_ms": trace.latency_ms,
                "agent_run_id": trace.agent_run_id,
            }
            for trace in traces
            if trace.latency_ms is not None
        ][:5],
        "retries": retries,
        "needs_attention": [
            {"id": item.id, "action_type": item.action_type.value, "hint": None}
            for item in attention
        ],
        "integration_failures": [
            {
                "id": run.id,
                "status": run.status.value,
                "error": run.last_error,
                "hint": _HINTS.get(run.last_error or ""),
            }
            for run in workflow_failures
        ],
        "duration_buckets": []
        if not include_platform
        else _buckets([trace.latency_ms for trace in traces if trace.latency_ms is not None]),
        "cost_usd": None if not include_platform or not costs else round(sum(costs), 8),
        "cost_notice": ""
        if not include_platform
        else (
            "Cost is unavailable unless token prices are configured "
            "and the provider reported usage."
        ),
        "platform_visible": include_platform,
        "workers": _present_workers(workers, now) if include_platform else [],
        "activity": _activity(db, organization_id, scope, now),
        "ingestion_jobs": [
            {
                "id": row.id,
                "document_id": row.document_id,
                "status": row.status.value,
                "attempts": row.attempts,
                "max_attempts": row.max_attempts,
                "error_code": row.error_message,
                "next_attempt_at": row.next_attempt_at,
                "updated_at": row.updated_at,
            }
            for row in ingestion
        ],
    }


def _activity(
    db: Session,
    organization_id: uuid.UUID,
    scope: DataScope,
    now: datetime,
) -> dict[str, Any]:
    cutoff = now - _RECENT
    assistant_rows = list(
        db.scalars(
            select(OperationTrace)
            .where(
                OperationTrace.organization_id == organization_id,
                OperationTrace.operation == "assistant_response",
            )
            .order_by(OperationTrace.started_at.desc())
            .limit(50)
        )
    )
    recent = [row for row in assistant_rows if _aware(row.started_at) >= cutoff]
    earlier_errors = [
        row for row in assistant_rows if _aware(row.started_at) < cutoff and row.status == "failed"
    ]
    if not recent:
        assistant_status = "quiet"
    elif recent[0].status == "failed":
        assistant_status = "errors"
    else:
        assistant_status = "available"
    recent_errors = [row for row in recent if row.status == "failed"]
    documents = _count_map(
        db.execute(
            select(Document.status, func.count())
            .where(
                Document.organization_id == organization_id,
                Document.archived_at.is_(None),
            )
            .group_by(Document.status)
        ).all()
    )
    jobs = list(
        db.scalars(
            select(IngestionJob)
            .where(IngestionJob.organization_id == organization_id)
            .order_by(IngestionJob.updated_at.desc())
            .limit(50)
        )
    )
    workflow_counts = _count_map(
        db.execute(
            select(WorkflowRun.status, func.count())
            .where(*_scoped(WorkflowRun, organization_id, scope))
            .group_by(WorkflowRun.status)
        ).all()
    )
    email_counts = _count_map(
        db.execute(
            select(EmailMessage.status, func.count())
            .where(*_scoped(EmailMessage, organization_id, scope))
            .group_by(EmailMessage.status)
        ).all()
    )
    pending = list(
        db.scalars(
            select(Approval)
            .where(
                *_scoped(Approval, organization_id, scope),
                Approval.status == ApprovalStatus.pending,
            )
            .order_by(Approval.created_at.asc())
            .limit(50)
        )
    )
    delayed = [item for item in pending if now - _aware(item.created_at) >= _RECENT]
    oldest = None
    if pending:
        oldest = round((now - _aware(pending[0].created_at)).total_seconds() / 3600, 1)
    connections, incidents = _integration_health(db, organization_id, now)
    return {
        "notice": _ACTIVITY_NOTICE,
        "assistant": {
            "status": assistant_status,
            "recent_replies": len(recent),
            "recent_errors": len(recent_errors),
            "last_error_code": None if not recent_errors else recent_errors[0].error_code,
            "earlier_errors": len(earlier_errors),
        },
        "knowledge": {
            "ready": documents.get(DocumentStatus.ready.value, 0),
            "indexing": documents.get(DocumentStatus.pending.value, 0)
            + documents.get(DocumentStatus.processing.value, 0),
            "failed": documents.get(DocumentStatus.failed.value, 0),
            "retrying": sum(
                1
                for job in jobs
                if job.status
                in {
                    IngestionJobStatus.queued,
                    IngestionJobStatus.running,
                    IngestionJobStatus.retrying,
                }
            ),
        },
        "workflows": {
            "running": workflow_counts.get(WorkflowStatus.pending.value, 0)
            + workflow_counts.get(WorkflowStatus.dispatching.value, 0)
            + workflow_counts.get(WorkflowStatus.accepted.value, 0),
            "needs_attention": workflow_counts.get(WorkflowStatus.needs_attention.value, 0),
            "failed": workflow_counts.get(WorkflowStatus.failed.value, 0),
            "completed": workflow_counts.get(WorkflowStatus.completed.value, 0),
        },
        "integrations": connections,
        "connection_incidents": incidents,
        "delivery": {
            "sent": email_counts.get(EmailStatus.sent.value, 0),
            "failed": email_counts.get(EmailStatus.failed.value, 0),
            "needs_attention": email_counts.get(EmailStatus.needs_attention.value, 0),
        },
        "approvals": {
            "pending": len(pending),
            "delayed": len(delayed),
            "oldest_pending_hours": oldest,
        },
        "recoverable": _recoverable(
            jobs, workflow_counts, pending_attention=_attention_rows(db, organization_id, scope)
        ),
    }


def _integration_health(
    db: Session, organization_id: uuid.UUID, now: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cutoff = now - _RECENT
    traces = list(
        db.scalars(
            select(OperationTrace)
            .where(
                OperationTrace.organization_id == organization_id,
                OperationTrace.status == "failed",
                OperationTrace.provider.is_not(None),
            )
            .order_by(OperationTrace.started_at.desc())
            .limit(40)
        )
    )
    recent_errors: dict[str, str | None] = {}
    incidents: list[dict[str, Any]] = []
    for trace in traces:
        provider = trace.provider or ""
        if _aware(trace.started_at) >= cutoff:
            recent_errors.setdefault(provider, trace.error_code)
            continue
        if len(incidents) < 10:
            incidents.append(
                {
                    "provider": provider,
                    "operation": trace.operation,
                    "error_code": trace.error_code,
                    "at": trace.started_at,
                }
            )
    configs = list(
        db.scalars(
            select(IntegrationConfig)
            .where(IntegrationConfig.organization_id == organization_id)
            .order_by(IntegrationConfig.integration_type)
        )
    )
    rows = [
        _connection_row(
            item.integration_type.value,
            item.provider,
            item.status.value,
            item.verified_at,
            item.verification_detail,
            recent_errors.get(item.provider),
        )
        for item in configs
    ]
    calendar = db.get(GoogleCalendarConnection, organization_id)
    if calendar is not None:
        verified_at = calendar.connected_at if calendar.encrypted_token else None
        stored_status = "disabled" if not calendar.encrypted_token else "configured"
        if calendar.connection_error:
            stored_status = "verification_failed"
        rows.append(
            _connection_row(
                "calendar",
                "google",
                stored_status,
                verified_at,
                calendar.connection_error,
                recent_errors.get("google"),
            )
        )
    return rows, incidents


def _connection_row(
    kind: str,
    provider: str,
    stored_status: str,
    verified_at: datetime | None,
    detail: str | None,
    recent_error: str | None,
) -> dict[str, Any]:
    health = _connection_health(stored_status, verified_at, detail, recent_error)
    recovery, href = _connection_recovery(health)
    return {
        "type": kind,
        "provider": provider,
        "status": stored_status,
        "verified": health == "connected",
        "health": health,
        "verified_at": verified_at,
        "recovery": recovery,
        "recovery_href": href,
    }


def _connection_health(
    stored_status: str,
    verified_at: datetime | None,
    detail: str | None,
    recent_error: str | None,
) -> str:
    evidence = f"{detail or ''} {recent_error or ''}".lower()
    if _contains_any(
        evidence, ("unauthor", "forbidden", "permission", "invalid_api", "credential")
    ):
        return "authentication_required"
    if _contains_any(evidence, ("timeout", "unreachable", "unavailable")):
        return "unavailable"
    if stored_status == "verification_failed" or recent_error:
        return "failed"
    if verified_at is not None and stored_status != "disabled":
        return "connected"
    return "configured"


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _connection_recovery(health: str) -> tuple[str | None, str | None]:
    if health == "authentication_required":
        return "Open Integrations and sign in again. This does not send a message.", "/integrations"
    if health == "failed":
        return (
            "Open Integrations and run the connection test. The test does not send a message.",
            "/integrations",
        )
    if health == "unavailable":
        return (
            "The last stored check could not reach the provider. Try the connection test later.",
            "/integrations",
        )
    if health == "configured":
        return "Saved. A successful verification is not stored yet.", "/integrations"
    return None, None


def _attention_rows(db: Session, organization_id: uuid.UUID, scope: DataScope) -> list[Approval]:
    return list(
        db.scalars(
            select(Approval)
            .where(
                *_scoped(Approval, organization_id, scope),
                Approval.status == ApprovalStatus.needs_attention,
            )
            .limit(20)
        )
    )


def _recoverable(
    jobs: list[IngestionJob],
    workflow_counts: dict[Any, int],
    *,
    pending_attention: list[Approval],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for job in jobs:
        retryable = job.status in {
            IngestionJobStatus.queued,
            IngestionJobStatus.running,
            IngestionJobStatus.retrying,
        } or (job.status == IngestionJobStatus.failed and job.attempts < job.max_attempts)
        if not retryable:
            continue
        items.append(
            {
                "kind": "indexing",
                "id": str(job.document_id),
                "summary": f"{job.status.value} · {job.attempts}/{job.max_attempts}",
            }
        )
    if workflow_counts.get(WorkflowStatus.needs_attention.value, 0):
        items.append(
            {
                "kind": "workflow",
                "id": None,
                "summary": "A workflow run is waiting on an uncertain outcome.",
            }
        )
    for approval in pending_attention:
        items.append(
            {
                "kind": "approval",
                "id": str(approval.id),
                "summary": approval.action_type.value,
            }
        )
    return items[:20]


def _count_map(rows: list[Any]) -> dict[str, int]:
    counted: dict[str, int] = {}
    for status, count in rows:
        key = status.value if hasattr(status, "value") else str(status)
        counted[key] = int(count)
    return counted


def _present_workers(rows: list[WorkerHeartbeat], now: datetime) -> list[dict[str, Any]]:
    grouped: dict[str, list[WorkerHeartbeat]] = {}
    for row in rows:
        grouped.setdefault(row.worker_kind, []).append(row)
    presented: list[dict[str, Any]] = []
    for group in grouped.values():
        group.sort(key=lambda item: _aware(item.heartbeat_at), reverse=True)
        current = group[0]
        presented.append(_worker_row(current, _current_status(current, now), "current"))
        for previous in group[1:]:
            presented.append(_worker_row(previous, "replaced", "previous"))
    return presented


def _current_status(row: WorkerHeartbeat, now: datetime) -> str:
    if row.status == "error":
        return "error"
    age = (now - _aware(row.heartbeat_at)).total_seconds()
    if age <= _FRESH_SECONDS:
        return row.status
    return "stopped"


def _worker_row(row: WorkerHeartbeat, status: str, generation: str) -> dict[str, Any]:
    return {
        "id": row.worker_id,
        "kind": row.worker_kind,
        "status": status,
        "generation": generation,
        "heartbeat_at": row.heartbeat_at,
        "last_success_at": row.last_success_at,
        "processed_count": row.processed_count,
        "last_error_code": row.last_error_code,
    }


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


def _scoped(model: Any, organization_id: uuid.UUID, scope: DataScope) -> list[Any]:
    filters = [model.organization_id == organization_id]
    clause = scope_clause(model.origin, scope)
    if clause is not None:
        filters.append(clause)
    return filters


def trace_run(db: Session, organization_id: uuid.UUID, run_id: uuid.UUID) -> dict[str, Any]:
    run = db.get(AgentRun, run_id)
    if run is None or run.organization_id != organization_id:
        raise AppError(404, "not_found", "Resource not found")
    inquiry = db.get(Inquiry, run.inquiry_id)
    events = list(
        db.scalars(
            select(AgentEvent)
            .where(AgentEvent.run_id == run.id, AgentEvent.organization_id == organization_id)
            .order_by(AgentEvent.created_at.asc())
        )
    )
    approvals = list(
        db.scalars(
            select(Approval)
            .where(Approval.run_id == run.id, Approval.organization_id == organization_id)
            .order_by(Approval.created_at.asc())
        )
    )
    workflows = list(
        db.scalars(
            select(WorkflowRun).where(
                WorkflowRun.agent_run_id == run.id,
                WorkflowRun.organization_id == organization_id,
            )
        )
    )
    traces = list(
        db.scalars(
            select(OperationTrace).where(
                OperationTrace.agent_run_id == run.id,
                OperationTrace.organization_id == organization_id,
            )
        )
    )
    lead_id = None if inquiry is None else inquiry.lead_id
    emails = []
    bookings = []
    if lead_id is not None:
        emails = list(
            db.scalars(
                select(EmailMessage).where(
                    EmailMessage.organization_id == organization_id,
                    EmailMessage.lead_id == lead_id,
                )
            )
        )
        bookings = list(
            db.scalars(
                select(CalendarBooking).where(
                    CalendarBooking.organization_id == organization_id,
                    CalendarBooking.lead_id == lead_id,
                )
            )
        )
    return {
        "hint_notice": "Hints name a recorded error code. They are not a root-cause finding.",
        "inquiry": None
        if inquiry is None
        else {"id": inquiry.id, "subject": inquiry.subject, "lead_id": inquiry.lead_id},
        "run": {
            "id": run.id,
            "status": run.status.value,
            "error_code": run.error_code,
            "hint": _HINTS.get(run.error_code or ""),
        },
        "events": [{"step": event.step, "status": event.status} for event in events],
        "approvals": [
            {"id": item.id, "action_type": item.action_type.value, "status": item.status.value}
            for item in approvals
        ],
        "workflows": [
            {
                "id": item.id,
                "status": item.status.value,
                "error": item.last_error,
                "hint": _HINTS.get(item.last_error or ""),
            }
            for item in workflows
        ],
        "traces": [
            {
                "operation": item.operation,
                "status": item.status,
                "latency_ms": item.latency_ms,
                "tokens_in": item.tokens_in,
                "tokens_out": item.tokens_out,
                "cost_usd": item.cost_usd,
                "error_code": item.error_code,
                "langfuse_status": item.langfuse_status,
            }
            for item in traces
        ],
        "emails": [
            {"id": item.id, "status": item.status.value, "mode": item.mode} for item in emails
        ],
        "bookings": [
            {"id": item.id, "status": item.status.value, "provider": item.provider}
            for item in bookings
        ],
    }


def _buckets(values: list[int]) -> list[dict[str, Any]]:
    bounds = [
        ("under_100ms", 0, 100),
        ("under_500ms", 100, 500),
        ("under_2s", 500, 2000),
        ("over_2s", 2000, None),
    ]
    buckets = []
    for name, low, high in bounds:
        count = sum(1 for value in values if value >= low and (high is None or value < high))
        buckets.append({"bucket": name, "count": count})
    return buckets
