"""Anonymous entry into a short-lived Harbor & Co. demonstration."""

from datetime import datetime

from fastapi import APIRouter, Request
from starlette.responses import Response

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import attach_session_cookie
from app.domains.demo.access import launch_is_limited, note_launch
from app.domains.demo.service import DEMO_TTL, launch_visitor, restart_visitor
from app.domains.identity.dependencies import CsrfSession, DbSession
from app.domains.identity.models import User
from app.domains.identity.schemas import AuthResponse, membership_out, user_out
from app.domains.identity.service import list_memberships

router = APIRouter(prefix="/demo", tags=["demo"])


def _client_key(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _response(db: DbSession, user: User, csrf_token: str, expires_at: datetime) -> AuthResponse:
    memberships = [
        membership_out(organization, membership.role, membership.id)
        for organization, membership in list_memberships(db, user.id)
    ]
    return AuthResponse(
        user=user_out(user),
        memberships=memberships,
        csrf_token=csrf_token,
        demo=True,
        demo_expires_at=expires_at,
    )


@router.post("/sessions", response_model=AuthResponse)
def start_demo(request: Request, response: Response, db: DbSession) -> AuthResponse:
    client_key = _client_key(request)
    if launch_is_limited(client_key):
        raise AppError(429, "rate_limited", "Too many demo sessions. Wait and try again.")
    note_launch(client_key)
    user, record = launch_visitor(db)
    attach_session_cookie(
        response,
        get_settings(),
        record.id,
        max_age=int(DEMO_TTL.total_seconds()),
    )
    return _response(db, user, record.csrf_token, record.expires_at)


@router.post("/sessions/restart", response_model=AuthResponse)
def restart_demo(
    request: Request, response: Response, db: DbSession, session: CsrfSession
) -> AuthResponse:
    client_key = _client_key(request)
    if launch_is_limited(client_key):
        raise AppError(429, "rate_limited", "Too many demo sessions. Wait and try again.")
    note_launch(client_key)
    user, record = restart_visitor(db, session)
    attach_session_cookie(
        response,
        get_settings(),
        record.id,
        max_age=int(DEMO_TTL.total_seconds()),
    )
    return _response(db, user, record.csrf_token, record.expires_at)
