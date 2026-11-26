"""Durable background dispatch for persisted automation intents."""

from __future__ import annotations

import logging
import threading

import structlog
from sqlalchemy import select

from app.core.database import SessionLocal
from app.domains.automation.intents import dispatch_intent
from app.domains.automation.models import ExecutionIntent, IntentStatus, WorkflowRun, WorkflowStatus
from app.domains.automation.workflows import dispatch_scheduled, dispatch_workflow
from app.domains.campaigns.dispatch import dispatch_due
from app.domains.observability.workers import touch

logger = structlog.get_logger(__name__)
_stdlib_logger = logging.getLogger(__name__)


def run_once() -> int:
    """Dispatch pending approval intents and workflow runs.

    Claiming remains in ``dispatch_intent`` so multiple worker processes are safe.
    """
    session = SessionLocal()
    try:
        worker_id = "automation-process"
        touch(session, worker_id, "automation", status="idle")
        dispatch_scheduled(session)
        pending = list(
            session.execute(
                select(ExecutionIntent.id, ExecutionIntent.organization_id).where(
                    ExecutionIntent.status == IntentStatus.pending
                )
            ).all()
        )
        processed = 0
        for intent_id, organization_id in pending:
            try:
                dispatch_intent(session, organization_id, intent_id)
            except Exception:
                session.rollback()
                logger.exception("automation_intent_failed", intent_id=str(intent_id))
            processed += 1
        workflows = session.execute(
            select(WorkflowRun.id, WorkflowRun.organization_id)
            .where(WorkflowRun.status == WorkflowStatus.pending)
            .order_by(WorkflowRun.created_at, WorkflowRun.id)
            .limit(50)
        ).all()
        for run_id, organization_id in workflows:
            try:
                dispatch_workflow(session, organization_id, run_id)
            except Exception:
                session.rollback()
                logger.exception("automation_workflow_failed", workflow_run_id=str(run_id))
            processed += 1
        try:
            processed += dispatch_due(session)
        except Exception:
            session.rollback()
            logger.exception("campaign_dispatch_failed")
            raise
        if processed:
            logger.info("automation_worker_processed", count=processed)
            touch(session, worker_id, "automation", status="idle", success=True)
        return processed
    except Exception as exc:
        try:
            touch(
                session,
                "automation-process",
                "automation",
                status="error",
                error=type(exc).__name__,
            )
        except Exception:
            session.rollback()
        raise
    finally:
        session.close()


def start(stop_event: threading.Event, interval_seconds: float = 1.0) -> threading.Thread:
    def loop() -> None:
        logger.info("automation_worker_loop_started")
        while not stop_event.is_set():
            try:
                run_once()
            except Exception:
                logger.exception("automation_worker_poll_failed")
                _stdlib_logger.exception("automation_worker_poll_failed")
            stop_event.wait(interval_seconds)
        logger.info("automation_worker_loop_stopped")

    logger.info("automation_worker_started", interval_seconds=interval_seconds)
    _stdlib_logger.info("automation_worker_started interval_seconds=%s", interval_seconds)
    thread = threading.Thread(target=loop, name="atlas-automation-worker", daemon=True)
    thread.start()
    return thread


def stop(stop_event: threading.Event, thread: threading.Thread) -> None:
    stop_event.set()
    thread.join(timeout=5)
