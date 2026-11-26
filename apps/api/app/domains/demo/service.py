"""Create, expire, and remove an isolated demonstration organization."""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, exists, func, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.domains.assistant.models import Message, MessageRole
from app.domains.demo import access as demo_access
from app.domains.demo.access import (
    MAX_ASSISTANT_REPLIES,
    MAX_DOCUMENTS,
    MAX_KNOWLEDGE_BYTES,
    MAX_UPLOAD_BYTES,
    SESSION_MINUTES,
    VISITOR_EMAIL_DOMAIN,
    VISITOR_PREFIX,
    forget_demo_request,
    is_visitor_email,
    is_visitor_slug,
    launch_blocked_reason,
)
from app.domains.demo.records import populate_visitor
from app.domains.identity.models import Membership, MembershipRole, Organization, User, UserSession
from app.domains.identity.service import list_memberships, start_session
from app.domains.knowledge.models import Document

DEMO_TTL = timedelta(minutes=SESSION_MINUTES)
# One process-wide lock so two launches cannot both pass the active-organization count.
VISITOR_LAUNCH_LOCK = 88421026


def launch_visitor(db: Session) -> tuple[User, UserSession]:
    reason = launch_blocked_reason(get_settings())
    if reason is not None:
        raise AppError(403, "demo_unavailable", reason)
    connection = _acquire_launch_lock()
    try:
        return _open_visitor(db)
    finally:
        _release_launch_lock(connection)


def _open_visitor(db: Session) -> tuple[User, UserSession]:
    cleanup_expired(db)
    active = _active_visitor_count(db)
    if active >= demo_access.MAX_ACTIVE_VISITORS:
        raise AppError(
            429,
            "demo_limited",
            "The demonstration is full. Try again after a session expires.",
        )
    user, organization = _create_visitor(db)
    try:
        populate_visitor(db, organization, user)
    except Exception:
        _delete_visitor(db, organization)
        raise
    return user, start_session(db, user, DEMO_TTL)


def _acquire_launch_lock() -> Connection:
    from app.core.database import engine

    connection = engine.connect()
    try:
        connection.execute(text(f"SELECT pg_advisory_lock({VISITOR_LAUNCH_LOCK})"))
        connection.commit()
    except Exception:
        connection.close()
        raise
    return connection


def _release_launch_lock(connection: Connection) -> None:
    try:
        connection.execute(text(f"SELECT pg_advisory_unlock({VISITOR_LAUNCH_LOCK})"))
        connection.commit()
    finally:
        connection.close()


def restart_visitor(db: Session, session: UserSession) -> tuple[User, UserSession]:
    user = db.get(User, session.user_id)
    if user is None or not is_visitor_email(user.email):
        raise AppError(403, "demo_restricted", "Restart is available for a demonstration session.")
    memberships = list_memberships(db, user.id)
    if len(memberships) != 1 or not is_visitor_slug(memberships[0][0].slug):
        raise AppError(403, "demo_restricted", "Restart is available for a demonstration session.")
    forget_demo_request(str(session.id))
    _delete_visitor(db, memberships[0][0])
    return launch_visitor(db)


def cleanup_expired(db: Session) -> int:
    now = datetime.now(UTC)
    active_member = exists(
        select(Membership.id).where(
            Membership.organization_id == Organization.id,
            exists(
                select(UserSession.id).where(
                    UserSession.user_id == Membership.user_id,
                    UserSession.revoked_at.is_(None),
                    UserSession.expires_at > now,
                )
            ),
        )
    )
    rows = list(
        db.scalars(
            select(Organization).where(
                Organization.slug.like(f"{VISITOR_PREFIX}%"),
                ~active_member,
            )
        ).all()
    )
    for organization in rows:
        _delete_visitor(db, organization)
    return len(rows)


def enforce_demo_assistant(db: Session, organization: Organization) -> None:
    if not is_visitor_slug(organization.slug):
        return
    count = db.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.organization_id == organization.id,
            Message.role == MessageRole.assistant,
        )
    )
    if int(count or 0) >= MAX_ASSISTANT_REPLIES:
        raise AppError(
            429,
            "demo_limited",
            "This demo session reached its assistant limit. Restart the demonstration.",
        )


def enforce_demo_upload(db: Session, organization: Organization, extra_bytes: int) -> None:
    if not is_visitor_slug(organization.slug):
        return
    if extra_bytes > MAX_UPLOAD_BYTES:
        raise AppError(
            422,
            "demo_limited",
            "Demo uploads are limited to 200 KB.",
        )
    count, total = db.execute(
        select(func.count(), func.coalesce(func.sum(Document.byte_size), 0)).where(
            Document.organization_id == organization.id
        )
    ).one()
    if int(count) >= MAX_DOCUMENTS:
        raise AppError(
            422,
            "demo_limited",
            "This demo session reached its document limit.",
        )
    if int(total) + extra_bytes > MAX_KNOWLEDGE_BYTES:
        raise AppError(
            422,
            "demo_limited",
            "This demo session reached its storage limit.",
        )


def _active_visitor_count(db: Session) -> int:
    now = datetime.now(UTC)
    return int(
        db.scalar(
            select(func.count())
            .select_from(Organization)
            .where(
                Organization.slug.like(f"{VISITOR_PREFIX}%"),
                exists(
                    select(Membership.id).where(
                        Membership.organization_id == Organization.id,
                        exists(
                            select(UserSession.id).where(
                                UserSession.user_id == Membership.user_id,
                                UserSession.revoked_at.is_(None),
                                UserSession.expires_at > now,
                            )
                        ),
                    )
                ),
            )
        )
        or 0
    )


def _create_visitor(db: Session) -> tuple[User, Organization]:
    token = uuid.uuid4().hex
    user = User(
        email=f"visitor-{token}{VISITOR_EMAIL_DOMAIN}",
        full_name="Harbor visitor",
        password_hash=hash_password(uuid.uuid4().hex),
        is_active=True,
    )
    organization = Organization(name="Harbor & Co.", slug=f"{VISITOR_PREFIX}{token[:12]}")
    db.add(user)
    db.add(organization)
    db.flush()
    db.add(
        Membership(
            user_id=user.id,
            organization_id=organization.id,
            role=MembershipRole.admin,
        )
    )
    db.commit()
    db.refresh(user)
    db.refresh(organization)
    return user, organization


def _delete_visitor(db: Session, organization: Organization) -> None:
    if not is_visitor_slug(organization.slug):
        raise AppError(403, "demo_restricted", "Only a demonstration workspace can be removed.")
    user_ids = list(
        db.scalars(
            select(Membership.user_id).where(Membership.organization_id == organization.id)
        ).all()
    )
    _remove_files(organization.id)
    organization_id = organization.id
    db.execute(delete(Organization).where(Organization.id == organization_id))
    if user_ids:
        db.execute(
            delete(User).where(
                User.id.in_(user_ids),
                User.email.like(f"%{VISITOR_EMAIL_DOMAIN}"),
                ~exists(select(Membership.id).where(Membership.user_id == User.id)),
            )
        )
    db.commit()


def _remove_files(organization_id: uuid.UUID) -> None:
    root = Path(get_settings().upload_storage_dir).expanduser().resolve()
    target = (root / str(organization_id)).resolve()
    if target.is_relative_to(root) and target.is_dir():
        shutil.rmtree(target)
