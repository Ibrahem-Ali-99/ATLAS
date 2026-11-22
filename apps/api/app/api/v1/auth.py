from datetime import timedelta

import structlog
from fastapi import APIRouter
from starlette.responses import Response

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import attach_session_cookie, clear_session_cookie
from app.domains.identity.dependencies import CsrfSession, CurrentSession, CurrentUser, DbSession
from app.domains.identity.models import User
from app.domains.identity.schemas import AuthResponse, LoginRequest, membership_out, user_out
from app.domains.identity.service import (
    authenticate,
    list_memberships,
    revoke_session,
    start_session,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth")


def _auth_response(db: DbSession, user: User, csrf_token: str) -> AuthResponse:
    memberships = [
        membership_out(organization, membership.role, membership.id)
        for organization, membership in list_memberships(db, user.id)
    ]
    return AuthResponse(user=user_out(user), memberships=memberships, csrf_token=csrf_token)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, response: Response, db: DbSession) -> AuthResponse:
    user = authenticate(db, body.email, body.password)
    if user is None:
        logger.info("login_failed")
        raise AppError(401, "invalid_credentials", "Invalid email or password")
    settings = get_settings()
    record = start_session(db, user, timedelta(hours=settings.session_ttl_hours))
    attach_session_cookie(response, settings, record.id)
    logger.info("login_succeeded", user_id=str(user.id))
    return _auth_response(db, user, record.csrf_token)


@router.post("/logout", status_code=204)
def logout(db: DbSession, session: CsrfSession) -> Response:
    revoke_session(db, session)
    response = Response(status_code=204)
    clear_session_cookie(response, get_settings())
    logger.info("logout", user_id=str(session.user_id))
    return response


@router.get("/me", response_model=AuthResponse)
def me(db: DbSession, user: CurrentUser, session: CurrentSession) -> AuthResponse:
    return _auth_response(db, user, session.csrf_token)
