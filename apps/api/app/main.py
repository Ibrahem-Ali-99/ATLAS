from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.environment)
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
        from app.domains.automation.intents import recover_intents
        from app.domains.automation.workflows import recover_workflows

        session = SessionLocal()
        try:
            recover_intents(session)
            recover_workflows(session)
        finally:
            session.close()
    except Exception:
        logger.error("automation_recovery_failed")
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.environment)
    docs_url = None if settings.environment == "production" else "/docs"
    openapi_url = None if settings.environment == "production" else "/openapi.json"
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
        expose_headers=["X-Request-ID"],
    )
    app.include_router(v1_router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": "atlas-api"}

    return app


app = create_app()
