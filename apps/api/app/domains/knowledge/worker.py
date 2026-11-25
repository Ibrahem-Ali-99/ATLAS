"""Durable PostgreSQL-backed knowledge ingestion worker."""
from __future__ import annotations

import logging
import threading
import uuid

import structlog

from app.core.database import SessionLocal
from app.domains.knowledge.service import claim_ingestion_job, run_ingestion_job
from app.domains.observability.workers import touch

logger = structlog.get_logger(__name__)
stdlib_logger = logging.getLogger(__name__)


def run_once(worker_id: str | None = None) -> bool:
    effective_worker_id = worker_id or str(uuid.uuid4())
    heartbeat = SessionLocal()
    touch(heartbeat, effective_worker_id, "knowledge", status="idle")
    heartbeat.close()
    job = claim_ingestion_job(effective_worker_id)
    if job is None:
        return False
    try:
        run_ingestion_job(job, effective_worker_id)
        heartbeat = SessionLocal()
        touch(heartbeat, effective_worker_id, "knowledge", status="idle", success=True)
        heartbeat.close()
    except Exception:
        logger.exception("knowledge_ingestion_job_failed", job_id=str(job.id))
        stdlib_logger.exception("knowledge_ingestion_job_failed job_id=%s", job.id)
        heartbeat = SessionLocal()
        touch(heartbeat, effective_worker_id, "knowledge", status="error", error="ingestion_failed")
        heartbeat.close()
    return True


def start(stop_event: threading.Event, interval_seconds: float = 1.0) -> threading.Thread:
    worker_id = str(uuid.uuid4())

    def loop() -> None:
        logger.info("knowledge_ingestion_worker_started", worker_id=worker_id)
        while not stop_event.is_set():
            try:
                run_once(worker_id)
            except Exception:
                logger.exception("knowledge_ingestion_worker_poll_failed")
            stop_event.wait(interval_seconds)
        logger.info("knowledge_ingestion_worker_stopped", worker_id=worker_id)

    thread = threading.Thread(target=loop, name="atlas-knowledge-worker", daemon=True)
    thread.start()
    return thread


def stop(stop_event: threading.Event, thread: threading.Thread) -> None:
    stop_event.set()
    thread.join(timeout=5)
