from datetime import timedelta

import structlog
from fastapi import APIRouter, Request
from starlette.responses import Response

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import attach_session_cookie, clear_session_cookie
from app.domains.identity.dependencies import CsrfSession, CurrentSession, CurrentUser, DbSession
from app.domains.identity.login_limit import (
    login_is_limited,
    note_login_failure,
    note_login_success,
)
from app.domains.identity.models import User
from app.domains.identity.schemas import (
    AuthResponse,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    membership_out,
    user_out,
)
from app.domains.identity.service import (
    authenticate,
    create_password_reset,
    list_memberships,
    normalize_email,
    reset_password,
    revoke_session,
    start_session,
)
from app.integrations.email import OutboundEmail, send_email

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth")


def _auth_response(db: DbSession, user: User, csrf_token: str) -> AuthResponse:
    memberships = [
        membership_out(organization, membership.role, membership.id)
        for organization, membership in list_memberships(db, user.id)
    ]
    return AuthResponse(user=user_out(user), memberships=memberships, csrf_token=csrf_token)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> AuthResponse:
    email = normalize_email(body.email)
    client_key = request.client.host if request.client is not None else "unknown"
    if login_is_limited(client_key, email):
        logger.info("login_rate_limited")
        raise AppError(429, "rate_limited", "Too many login attempts. Wait and try again.")
    user = authenticate(db, body.email, body.password)
    if user is None:
        note_login_failure(client_key, email)
        logger.info("login_failed")
        raise AppError(401, "invalid_credentials", "Invalid email or password")
    note_login_success(email)
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


@router.post("/forgot-password", status_code=202)
def forgot_password(body: PasswordResetRequest, db: DbSession) -> dict[str, str]:
    token = create_password_reset(db, str(body.email))
    if token:
        try:
            send_email(
                OutboundEmail(
                    recipient=str(body.email),
                    subject="Reset your ATLAS password",
                    body=f"Use this one-time reset token in the ATLAS password reset form: {token}",
                    idempotency_key=f"password-reset:{token}",
                )
            )
        except Exception:
            logger.warning("password_reset_delivery_failed", error_code="delivery_failed")
    return {"detail": "If the account exists, reset instructions have been sent."}


@router.post("/reset-password", status_code=204)
def confirm_password_reset(body: PasswordResetConfirm, db: DbSession) -> Response:
    reset_password(db, body.token, body.password)
    return Response(status_code=204)
