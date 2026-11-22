import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.agents.models import AgentEvent, AgentRun

logger = structlog.get_logger(__name__)


def add_event(
    db: Session,
    run: AgentRun,
    step: str,
    status: str,
    detail: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    db.add(
        AgentEvent(
            organization_id=run.organization_id,
            run_id=run.id,
            step=step[:80],
            status=status[:40],
            detail=detail or {},
            error_message=error_message[:500] if error_message else None,
        )
    )
    db.commit()
    if status == "failed":
        logger.error("agent_step_failed", run_id=str(run.id), step=step)
        return
    logger.info("agent_step", run_id=str(run.id), step=step, status=status)


def list_events(db: Session, organization_id: uuid.UUID, run_id: uuid.UUID) -> list[AgentEvent]:
    return list(
        db.scalars(
            select(AgentEvent)
            .where(AgentEvent.organization_id == organization_id, AgentEvent.run_id == run_id)
            .order_by(AgentEvent.created_at.asc())
        ).all()
    )
