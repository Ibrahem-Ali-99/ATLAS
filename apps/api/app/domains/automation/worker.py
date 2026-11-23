"""Durable background dispatch for persisted automation intents."""

from __future__ import annotations

import threading

import structlog
from sqlalchemy import select

from app.core.database import SessionLocal
from app.domains.automation.intents import dispatch_intent
from app.domains.automation.models import ExecutionIntent, IntentStatus

logger = structlog.get_logger(__name__)


def run_once() -> int:
    """Claim and dispatch each currently pending intent once.

    Claiming remains in ``dispatch_intent`` so multiple worker processes are safe.
    """
    session = SessionLocal()
    try:
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
                logger.exception("automation_intent_failed", intent_id=str(intent_id))
            processed += 1
        if processed:
            logger.info("automation_worker_processed", count=processed)
        return processed
    finally:
        session.close()


def start(stop_event: threading.Event, interval_seconds: float = 1.0) -> threading.Thread:
    def loop() -> None:
        while not stop_event.is_set():
            run_once()
            stop_event.wait(interval_seconds)

    logger.info("automation_worker_started")
    thread = threading.Thread(target=loop, name="atlas-automation-worker", daemon=True)
    thread.start()
    return thread


def stop(stop_event: threading.Event, thread: threading.Thread) -> None:
    stop_event.set()
    thread.join(timeout=5)
