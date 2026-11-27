import logging
import os
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import AtlasCorsMiddleware, RequestContextMiddleware

logger = structlog.get_logger(__name__)
_stdlib_logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.environment)
    from app.integrations.mcp_runtime import require_mcp_interpreter

    require_mcp_interpreter()
    logger.info("startup", environment=settings.environment)
    try:
        from app.domains.knowledge.service import resume_incomplete_documents

        resumed = resume_incomplete_documents()
        if resumed:
            logger.info("ingestion_resumed", documents=resumed)
    except Exception:
        logger.error("ingestion_resume_failed")
    try:
        from app.core.database import SessionLocal
        from app.domains.agents.service import recover_runs
        from app.domains.automation.intents import recover_intents
        from app.domains.automation.workflows import recover_workflows

        session = SessionLocal()
        try:
            recover_runs(session)
            recover_intents(session)
            recover_workflows(session)
        finally:
            session.close()
    except Exception:
        logger.error("automation_recovery_failed")
    try:
        from app.domains.agents.service import prepare_checkpoints

        prepare_checkpoints()
    except Exception:
        logger.error("checkpoint_setup_failed")
    worker_stop: threading.Event | None = None
    worker_thread: threading.Thread | None = None
    knowledge_worker_thread: threading.Thread | None = None
    worker_enabled = (
        settings.environment != "test" or os.environ.get("ATLAS_E2E_PROVIDER_TRANSPORT") == "1"
    )
    logger.info("automation_worker_enabled", enabled=worker_enabled)
    _stdlib_logger.info("automation_worker_enabled enabled=%s", worker_enabled)
    if worker_enabled:
        from app.domains.automation.worker import start

        worker_stop = threading.Event()
        worker_thread = start(worker_stop)
        from app.domains.knowledge.worker import start as start_knowledge

        knowledge_worker_thread = start_knowledge(worker_stop)
    yield
    if worker_stop is not None and worker_thread is not None:
        from app.domains.automation.worker import stop

        stop(worker_stop, worker_thread)
        if knowledge_worker_thread is not None:
            knowledge_worker_thread.join(timeout=5)
    else:
        logger.info("automation_worker_stopped", enabled=False)
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.environment)
    # The public portfolio stays in development so workspace chat can use the
    # deterministic provider. That process still must not publish the schema.
    hide_schema = settings.environment == "production" or settings.public_demo
    docs_url = None if hide_schema else "/docs"
    openapi_url = None if hide_schema else "/openapi.json"
    app = FastAPI(
        title="ATLAS API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=openapi_url,
    )
    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(AtlasCorsMiddleware, workspace_origins=settings.cors_origin_list)
    app.include_router(v1_router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": "atlas-api"}

    return app


app = create_app()
