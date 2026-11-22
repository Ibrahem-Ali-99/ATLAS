import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.errors import GraphInterrupt, UnknownInterruptError
from langgraph.types import Command
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.agents.events import add_event, list_events
from app.domains.agents.models import AgentEvent, AgentRun, RunStatus
from app.domains.agents.workflow import RunContext, bind_run, build_graph, release_run
from app.domains.approvals.models import Approval, ApprovalStatus
from app.domains.approvals.service import list_for_run
from app.domains.crm import service as crm
from app.domains.crm.models import Inquiry
from app.integrations.business_mcp import BusinessToolError, BusinessTools
from app.integrations.language import ChatClient

logger = structlog.get_logger(__name__)
_checkpoint_ready: set[str] = set()


def start_run(
    db: Session,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    inquiry_id: uuid.UUID,
    chat: ChatClient,
) -> AgentRun:
    crm.get_inquiry(db, organization_id, inquiry_id)
    run = AgentRun(
        organization_id=organization_id,
        inquiry_id=inquiry_id,
        started_by=actor_user_id,
        status=RunStatus.running,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info("agent_run_started", run_id=str(run.id), organization_id=str(organization_id))
    return _drive(db, run, chat, resume=False)


def resume_run(
    db: Session,
    organization_id: uuid.UUID,
    run_id: uuid.UUID,
    chat: ChatClient,
) -> AgentRun:
    run = get_run(db, organization_id, run_id)
    if run.status not in {RunStatus.awaiting_approval, RunStatus.running}:
        raise AppError(409, "invalid_transition", "This run cannot be resumed")
    if run.status == RunStatus.awaiting_approval and _has_pending(db, organization_id, run.id):
        raise AppError(
            409,
            "approval_required",
            "An admin has to approve or reject the proposed actions",
        )
    return _drive(db, run, chat, resume=True)


def get_run(db: Session, organization_id: uuid.UUID, run_id: uuid.UUID) -> AgentRun:
    run = db.scalar(
        select(AgentRun).where(AgentRun.id == run_id, AgentRun.organization_id == organization_id)
    )
    if run is None:
        raise AppError(404, "not_found", "Resource not found")
    return run


def list_runs(
    db: Session,
    organization_id: uuid.UUID,
    *,
    status: RunStatus | None,
    page: int,
    page_size: int,
) -> tuple[list[tuple[AgentRun, str]], int]:
    filters = [AgentRun.organization_id == organization_id]
    if status is not None:
        filters.append(AgentRun.status == status)
    total = db.scalar(select(func.count()).select_from(AgentRun).where(*filters)) or 0
    offset = (page - 1) * page_size
    rows = db.execute(
        select(AgentRun, Inquiry.subject)
        .join(Inquiry, Inquiry.id == AgentRun.inquiry_id)
        .where(*filters)
        .order_by(AgentRun.started_at.desc())
        .offset(offset)
        .limit(page_size)
    ).all()
    return [(row[0], row[1]) for row in rows], total


def run_events(db: Session, organization_id: uuid.UUID, run_id: uuid.UUID) -> list[AgentEvent]:
    get_run(db, organization_id, run_id)
    return list_events(db, organization_id, run_id)


def run_approvals(db: Session, organization_id: uuid.UUID, run_id: uuid.UUID) -> list[Approval]:
    get_run(db, organization_id, run_id)
    return list_for_run(db, organization_id, run_id)


def _drive(db: Session, run: AgentRun, chat: ChatClient, *, resume: bool) -> AgentRun:
    context = RunContext(
        db=db,
        organization_id=run.organization_id,
        actor_user_id=run.started_by,
        run_id=run.id,
        chat=chat,
        tools=BusinessTools(run.organization_id),
    )
    url = _checkpoint_url()
    config: RunnableConfig = {"configurable": {"thread_id": str(run.id)}}
    token = bind_run(context)
    try:
        with PostgresSaver.from_conn_string(url) as saver:
            if url not in _checkpoint_ready:
                saver.setup()
                _checkpoint_ready.add(url)
            graph = build_graph().compile(checkpointer=saver)
            try:
                _invoke(graph, config, context, resume)
            except GraphInterrupt:
                pass
            except UnknownInterruptError as exc:
                raise AppError(409, "invalid_transition", "This run cannot be resumed") from exc
            except AppError as exc:
                _mark_failed(db, run.id, exc)
                raise
            except BusinessToolError as exc:
                wrapped = AppError(502, "tool_failed", exc.message)
                _mark_failed(db, run.id, wrapped)
                raise wrapped from exc
            except Exception as exc:
                logger.error("agent_run_failed", run_id=str(run.id), error_type=type(exc).__name__)
                wrapped = AppError(500, "agent_failed", "The agent run failed")
                _mark_failed(db, run.id, wrapped)
                raise wrapped from exc
            snapshot = graph.get_state(config)
        _reconcile(db, run.id, snapshot)
    finally:
        release_run(token)
    finished = get_run(db, run.organization_id, run.id)
    if finished.status == RunStatus.completed:
        logger.info("agent_run_completed", run_id=str(finished.id))
    elif finished.status == RunStatus.awaiting_approval:
        logger.info("agent_run_paused", run_id=str(finished.id))
    return finished


def _invoke(graph: Any, config: RunnableConfig, context: RunContext, resume: bool) -> None:
    if not resume:
        graph.invoke({}, config, durability="sync")
        return
    snapshot = graph.get_state(config)
    if snapshot.interrupts:
        graph.invoke(Command(resume={"continue": True}), config, durability="sync")
        return
    if snapshot.next:
        graph.invoke(None, config, durability="sync")
        return
    raise AppError(409, "invalid_transition", "This run cannot be resumed")


def _reconcile(db: Session, run_id: uuid.UUID, snapshot: Any) -> None:
    run = db.get(AgentRun, run_id)
    if run is None or run.status in {RunStatus.completed, RunStatus.failed}:
        return
    paused = bool(getattr(snapshot, "interrupts", ())) or bool(getattr(snapshot, "next", ()))
    if paused:
        if run.status != RunStatus.awaiting_approval:
            run.status = RunStatus.awaiting_approval
            db.commit()
        return
    run.status = RunStatus.failed
    run.error_code = "agent_failed"
    run.error_message = "The agent stopped before recording an outcome"
    run.finished_at = datetime.now(UTC)
    db.commit()


def _mark_failed(db: Session, run_id: uuid.UUID, exc: AppError) -> None:
    db.rollback()
    run = db.get(AgentRun, run_id)
    if run is None or run.status == RunStatus.completed:
        return
    run.status = RunStatus.failed
    run.error_code = exc.code
    run.error_message = exc.message[:500]
    run.finished_at = datetime.now(UTC)
    db.commit()
    add_event(db, run, "run", "failed", {}, exc.message)
    logger.error("agent_run_failed", run_id=str(run.id), code=exc.code)


def _has_pending(db: Session, organization_id: uuid.UUID, run_id: uuid.UUID) -> bool:
    return any(
        item.status == ApprovalStatus.pending for item in list_for_run(db, organization_id, run_id)
    )


def _checkpoint_url() -> str:
    url = get_settings().database_url
    prefix = "postgresql+psycopg"
    if url.startswith(prefix):
        return "postgresql" + url.removeprefix(prefix)
    return url
