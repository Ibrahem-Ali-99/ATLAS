import structlog
from fastapi import APIRouter
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import database_is_reachable
from app.core.errors import AppError
from app.domains.identity.dependencies import DbSession
from app.domains.identity.schemas import HealthResponse, ReadyResponse

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="atlas-api")


@router.get("/ready", response_model=ReadyResponse)
def ready(db: DbSession) -> ReadyResponse:
    try:
        database_is_reachable(db)
    except SQLAlchemyError as exc:
        logger.warning("readiness_failed", error_type=exc.__class__.__name__)
        raise AppError(503, "not_ready", "Database is unavailable") from exc
    return ReadyResponse(status="ok", database="ok")
