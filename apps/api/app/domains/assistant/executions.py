"""Persist Assistant executions. Stored steps are operational, not model reasoning."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.domains.assistant.models import AssistantExecution, AssistantExecutionStep
from app.domains.assistant.schemas import AssistantStepOut
from app.domains.identity.models import MembershipRole

_SECRET_KEYS = {"api_key", "token", "password", "secret", "authorization", "credential"}


def begin_execution(
    db: Session,
    *,
    organization_id: uuid.UUID,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    user_message_id: uuid.UUID | None,
    request: str,
) -> AssistantExecution:
    row = AssistantExecution(
        organization_id=organization_id,
        conversation_id=conversation_id,
        user_id=user_id,
        user_message_id=user_message_id,
        request=request[:4000],
        status="running",
        selected_tools=[],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def add_step(
    db: Session,
    execution: AssistantExecution,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    status: str,
    duration_ms: int,
    records: list[dict[str, Any]],
    error_message: str | None = None,
    recovery: str | None = None,
) -> None:
    sequence = _step_count(db, execution.id) + 1
    if tool_name not in {"respond", "clarify"} and tool_name not in execution.selected_tools:
        execution.selected_tools = [*execution.selected_tools, tool_name]
        flag_modified(execution, "selected_tools")
    db.add(
        AssistantExecutionStep(
            organization_id=execution.organization_id,
            execution_id=execution.id,
            sequence=sequence,
            tool_name=tool_name[:80],
            arguments=_public_arguments(arguments),
            status=status,
            duration_ms=max(0, duration_ms),
            records=records[:8],
            error_message=None if error_message is None else error_message[:500],
            recovery=None if recovery is None else recovery[:500],
        )
    )
    db.commit()


def add_tokens(execution: AssistantExecution, prompt: int | None, completion: int | None) -> None:
    if isinstance(prompt, int):
        execution.tokens_in = (execution.tokens_in or 0) + prompt
    if isinstance(completion, int):
        execution.tokens_out = (execution.tokens_out or 0) + completion


def finish_execution(
    db: Session,
    execution_id: uuid.UUID | None,
    *,
    assistant_message_id: uuid.UUID | None,
    status: str = "completed",
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    if execution_id is None:
        return
    row = db.get(AssistantExecution, execution_id)
    if row is None or row.status != "running":
        return
    row.status = status
    row.assistant_message_id = assistant_message_id
    row.error_code = error_code
    row.error_message = None if error_message is None else error_message[:500]
    row.finished_at = datetime.now(UTC)
    db.commit()


def fail_for_conversation(
    db: Session, conversation_id: uuid.UUID, assistant_message_id: uuid.UUID, message: str
) -> None:
    row = db.scalar(
        select(AssistantExecution)
        .where(
            AssistantExecution.conversation_id == conversation_id,
            AssistantExecution.status == "running",
        )
        .order_by(AssistantExecution.started_at.desc())
    )
    if row is None:
        return
    row.status = "failed"
    row.assistant_message_id = assistant_message_id
    row.error_code = "provider_failed"
    row.error_message = message[:500]
    row.finished_at = datetime.now(UTC)
    db.commit()


def fail_execution(db: Session, execution_id: uuid.UUID | None, code: str, message: str) -> None:
    if execution_id is None:
        return
    db.rollback()
    row = db.get(AssistantExecution, execution_id)
    if row is None or row.status != "running":
        return
    row.status = "failed"
    row.error_code = code[:80]
    row.error_message = message[:500]
    row.finished_at = datetime.now(UTC)
    db.commit()


def steps_for_messages(
    db: Session, organization_id: uuid.UUID, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[AssistantStepOut]]:
    if not message_ids:
        return {}
    rows = db.execute(
        select(AssistantExecution, AssistantExecutionStep)
        .join(
            AssistantExecutionStep,
            AssistantExecutionStep.execution_id == AssistantExecution.id,
        )
        .where(
            AssistantExecution.organization_id == organization_id,
            AssistantExecution.assistant_message_id.in_(message_ids),
        )
        .order_by(AssistantExecutionStep.sequence.asc())
    ).all()
    grouped: dict[uuid.UUID, list[AssistantStepOut]] = {}
    for execution, step in rows:
        if execution.assistant_message_id is None:
            continue
        grouped.setdefault(execution.assistant_message_id, []).append(_step_out(step))
    return grouped


def steps_for_execution(
    db: Session, execution_id: uuid.UUID
) -> list[AssistantExecutionStep]:
    return list(
        db.scalars(
            select(AssistantExecutionStep)
            .where(AssistantExecutionStep.execution_id == execution_id)
            .order_by(AssistantExecutionStep.sequence.asc())
        ).all()
    )


def list_executions(
    db: Session,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    role: MembershipRole,
    *,
    page: int,
    page_size: int,
) -> tuple[list[AssistantExecution], int]:
    filters = [AssistantExecution.organization_id == organization_id]
    if role is not MembershipRole.admin:
        filters.append(AssistantExecution.user_id == user_id)
    total = db.scalar(select(func_count()).select_from(AssistantExecution).where(*filters)) or 0
    rows = list(
        db.scalars(
            select(AssistantExecution)
            .where(*filters)
            .order_by(AssistantExecution.started_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return rows, total


def get_execution(
    db: Session,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    role: MembershipRole,
    execution_id: uuid.UUID,
) -> tuple[AssistantExecution, list[AssistantExecutionStep]]:
    from app.core.errors import AppError

    row = db.scalar(
        select(AssistantExecution).where(
            AssistantExecution.id == execution_id,
            AssistantExecution.organization_id == organization_id,
        )
    )
    if row is None or (role is not MembershipRole.admin and row.user_id != user_id):
        raise AppError(404, "not_found", "Resource not found")
    steps = list(
        db.scalars(
            select(AssistantExecutionStep)
            .where(AssistantExecutionStep.execution_id == row.id)
            .order_by(AssistantExecutionStep.sequence.asc())
        ).all()
    )
    return row, steps


def func_count() -> Any:
    from sqlalchemy import func

    return func.count()


def _step_count(db: Session, execution_id: uuid.UUID) -> int:
    from sqlalchemy import func

    return (
        db.scalar(
            select(func.count())
            .select_from(AssistantExecutionStep)
            .where(AssistantExecutionStep.execution_id == execution_id)
        )
        or 0
    )


def _public_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in arguments.items():
        if key.lower() in _SECRET_KEYS:
            continue
        if isinstance(value, str):
            cleaned[key] = value[:500]
        elif isinstance(value, (int, float, bool)) or value is None:
            cleaned[key] = value
    return cleaned


def _step_out(step: AssistantExecutionStep) -> AssistantStepOut:
    if step.recovery:
        detail = step.recovery
    elif step.error_message:
        detail = step.error_message
    elif step.records:
        detail = _record_detail(step.records)
    else:
        detail = "Answered without a workspace lookup"
    return AssistantStepOut(
        tool_name=step.tool_name,
        status=step.status,  # type: ignore[arg-type]
        duration_ms=step.duration_ms,
        detail=detail,
    )


def _record_detail(records: list[dict[str, object]]) -> str:
    titles = [str(record.get("title")) for record in records if record.get("title")]
    if not titles:
        return "No matching records"
    shown = ", ".join(titles[:4])
    return shown[:200]
