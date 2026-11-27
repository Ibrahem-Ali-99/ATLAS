from datetime import timedelta
from urllib.parse import urlencode
from uuid import uuid4

import structlog
from fastapi import APIRouter, Request
from starlette.responses import Response

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import attach_session_cookie, clear_session_cookie
from app.domains.demo.access import is_visitor_email, is_visitor_slug
from app.domains.identity.dependencies import CsrfSession, CurrentSession, CurrentUser, DbSession
from app.domains.identity.login_limit import (
    login_is_limited,
    note_login_failure,
    note_login_success,
)
from app.domains.identity.models import User, UserSession
from app.domains.identity.schemas import (
    AuthResponse,
    LoginRequest,
    PasswordChange,
    PasswordResetConfirm,
    PasswordResetRequest,
    membership_out,
    user_out,
)
from app.domains.identity.service import (
    authenticate,
    create_password_reset,
    change_password,
    list_memberships,
    normalize_email,
    reset_password,
    revoke_session,
    start_session,
)
from app.integrations.email import OutboundEmail, send_email

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth")


def _auth_response(db: DbSession, user: User, session: UserSession) -> AuthResponse:
    memberships = [
        membership_out(organization, membership.role, membership.id)
        for organization, membership in list_memberships(db, user.id)
    ]
    demo = any(is_visitor_slug(item.organization_slug) for item in memberships)
    return AuthResponse(
        user=user_out(user),
        memberships=memberships,
        csrf_token=session.csrf_token,
        demo=demo,
        demo_expires_at=session.expires_at if demo else None,
    )


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> AuthResponse:
    email = normalize_email(body.email)
    client_key = request.client.host if request.client is not None else "unknown"
    if login_is_limited(client_key, email):
        logger.info("login_rate_limited")
        raise AppError(429, "rate_limited", "Too many login attempts. Wait and try again.")
    if is_visitor_email(email):
        note_login_failure(client_key, email)
        logger.info("login_failed")
        raise AppError(401, "invalid_credentials", "Invalid email or password")
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
    return _auth_response(db, user, record)


@router.post("/logout", status_code=204)
def logout(db: DbSession, session: CsrfSession) -> Response:
    revoke_session(db, session)
    response = Response(status_code=204)
    clear_session_cookie(response, get_settings())
    logger.info("logout", user_id=str(session.user_id))
    return response


@router.get("/me", response_model=AuthResponse)
def me(db: DbSession, user: CurrentUser, session: CurrentSession) -> AuthResponse:
    return _auth_response(db, user, session)


@router.post("/password", status_code=204)
def update_password(body: PasswordChange, db: DbSession, session: CsrfSession) -> Response:
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AppError(401, "unauthenticated", "Sign in to continue")
    change_password(db, user, session.id, body.current_password, body.new_password)
    logger.info("password_changed", user_id=str(user.id))
    return Response(status_code=204)


@router.post("/forgot-password", status_code=202)
def forgot_password(body: PasswordResetRequest, db: DbSession) -> dict[str, str]:
    allowed_origins = get_settings().cors_origin_list
    visitor = is_visitor_email(normalize_email(str(body.email)))
    token = None if visitor or not allowed_origins else create_password_reset(db, str(body.email))
    if token:
        web_url = allowed_origins[0]
        link = f"{web_url.rstrip('/')}/reset-password#{urlencode({'token': token})}"
        try:
            send_email(
                OutboundEmail(
                    recipient=str(body.email),
                    subject="Reset your ATLAS password",
                    body=f"Use this link within one hour to reset your ATLAS password:\n\n{link}",
                    idempotency_key=uuid4().hex,
                )
            )
        except Exception:
            logger.warning("password_reset_delivery_failed", error_code="delivery_failed")
    return {"detail": "If the account exists, reset instructions have been sent."}


@router.post("/reset-password", status_code=204)
def confirm_password_reset(body: PasswordResetConfirm, db: DbSession) -> Response:
    reset_password(db, body.token, body.password)
    return Response(status_code=204)
