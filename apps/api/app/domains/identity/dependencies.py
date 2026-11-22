import secrets
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.core.security import read_session_id
from app.domains.identity.models import Membership, MembershipRole, Organization, User, UserSession
from app.domains.identity.service import get_active_session, get_membership

DbSession = Annotated[Session, Depends(get_db)]


def get_current_session(request: Request, db: DbSession) -> UserSession:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise AppError(401, "unauthenticated", "Authentication required")
    session_id = read_session_id(token, settings.secret_key, settings.session_max_age_seconds)
    if session_id is None:
        raise AppError(401, "unauthenticated", "Authentication required")
    record = get_active_session(db, session_id)
    if record is None:
        raise AppError(401, "unauthenticated", "Authentication required")
    return record


CurrentSession = Annotated[UserSession, Depends(get_current_session)]


def get_current_user(db: DbSession, session: CurrentSession) -> User:
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AppError(401, "unauthenticated", "Authentication required")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_csrf(request: Request, session: CurrentSession) -> UserSession:
    provided = request.headers.get("x-csrf-token")
    if provided is None:
        raise AppError(403, "csrf_failed", "CSRF token missing or invalid")
    try:
        matches = secrets.compare_digest(provided, session.csrf_token)
    except (TypeError, ValueError):
        matches = False
    if not matches:
        raise AppError(403, "csrf_failed", "CSRF token missing or invalid")
    return session


CsrfSession = Annotated[UserSession, Depends(require_csrf)]


@dataclass(frozen=True)
class MemberContext:
    user: User
    organization: Organization
    membership: Membership


def require_member(organization_id: uuid.UUID, user: CurrentUser, db: DbSession) -> MemberContext:
    """Authorize from the session user. A client-supplied organization id is only a lookup key."""

    row = get_membership(db, user.id, organization_id)
    if row is None:
        raise AppError(404, "not_found", "Resource not found")
    organization, membership = row
    return MemberContext(user=user, organization=organization, membership=membership)


Member = Annotated[MemberContext, Depends(require_member)]


def require_member_csrf(_csrf: CsrfSession, member: Member) -> MemberContext:
    return member


CsrfMember = Annotated[MemberContext, Depends(require_member_csrf)]


def _role_value(role: MembershipRole | str) -> str:
    if isinstance(role, MembershipRole):
        return role.value
    return str(role)


def require_admin(context: Member) -> MemberContext:
    if _role_value(context.membership.role) != MembershipRole.admin.value:
        raise AppError(403, "forbidden", "Admin role is required for this resource")
    return context


Admin = Annotated[MemberContext, Depends(require_admin)]
