import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.domains.identity.models import Membership, MembershipRole, Organization, User, UserSession

_DUMMY_PASSWORD_HASH = hash_password("atlas-unused-dummy-password")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user


def start_session(db: Session, user: User, ttl: timedelta) -> UserSession:
    record = UserSession(
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(32),
        expires_at=datetime.now(UTC) + ttl,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def revoke_session(db: Session, record: UserSession) -> None:
    record.revoked_at = datetime.now(UTC)
    db.commit()


def get_active_session(db: Session, session_id: uuid.UUID) -> UserSession | None:
    record = db.get(UserSession, session_id)
    if record is None or record.revoked_at is not None:
        return None
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return None
    return record


def list_memberships(db: Session, user_id: uuid.UUID) -> list[tuple[Organization, Membership]]:
    rows = db.execute(
        select(Organization, Membership)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == user_id)
        .order_by(Organization.name.asc())
    ).all()
    return [(organization, membership) for organization, membership in rows]


def get_membership(
    db: Session, user_id: uuid.UUID, organization_id: uuid.UUID
) -> tuple[Organization, Membership] | None:
    row = db.execute(
        select(Organization, Membership)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == user_id, Membership.organization_id == organization_id)
    ).one_or_none()
    if row is None:
        return None
    organization, membership = row
    return organization, membership


def upsert_organization(db: Session, *, name: str, slug: str) -> Organization:
    organization = db.scalar(select(Organization).where(Organization.slug == slug))
    if organization is None:
        organization = Organization(name=name, slug=slug)
        db.add(organization)
        db.flush()
        return organization
    organization.name = name
    return organization


def upsert_user(db: Session, *, email: str, full_name: str, password: str) -> User:
    normalized = normalize_email(email)
    user = db.scalar(select(User).where(User.email == normalized))
    password_hash = hash_password(password)
    if user is None:
        user = User(
            email=normalized,
            full_name=full_name,
            password_hash=password_hash,
            is_active=True,
        )
        db.add(user)
        db.flush()
        return user
    user.full_name = full_name
    user.password_hash = password_hash
    user.is_active = True
    return user


def upsert_membership(
    db: Session, *, user: User, organization: Organization, role: MembershipRole
) -> Membership:
    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.organization_id == organization.id,
        )
    )
    if membership is None:
        membership = Membership(user_id=user.id, organization_id=organization.id, role=role)
        db.add(membership)
        db.flush()
        return membership
    membership.role = role
    return membership
