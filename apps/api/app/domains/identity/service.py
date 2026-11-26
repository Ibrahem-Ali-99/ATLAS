import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.domains.identity.models import (
    Membership,
    MembershipRole,
    Organization,
    PasswordResetToken,
    User,
    UserSession,
)

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


def list_team(db: Session, organization_id: uuid.UUID) -> list[tuple[Membership, User]]:
    return list(
        db.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.organization_id == organization_id)
            .order_by(User.full_name)
        ).all()
    )


def update_membership_role(
    db: Session,
    organization_id: uuid.UUID,
    membership_id: uuid.UUID,
    role: MembershipRole,
) -> Membership:
    membership = db.scalar(
        select(Membership)
        .where(
            Membership.id == membership_id,
            Membership.organization_id == organization_id,
        )
        .with_for_update()
    )
    if membership is None:
        raise AppError(404, "member_not_found", "Member not found")
    if membership.role == MembershipRole.admin and role != MembershipRole.admin:
        admins = (
            db.scalar(
                select(func.count())
                .select_from(Membership)
                .where(
                    Membership.organization_id == organization_id,
                    Membership.role == MembershipRole.admin,
                )
            )
            or 0
        )
        if admins <= 1:
            raise AppError(
                409,
                "last_admin",
                "The last organization administrator cannot be demoted",
            )
    membership.role = role
    return membership


def remove_membership(db: Session, organization_id: uuid.UUID, membership_id: uuid.UUID) -> None:
    membership = db.scalar(
        select(Membership)
        .where(
            Membership.id == membership_id,
            Membership.organization_id == organization_id,
        )
        .with_for_update()
    )
    if membership is None:
        raise AppError(404, "member_not_found", "Member not found")
    if membership.role == MembershipRole.admin:
        admins = (
            db.scalar(
                select(func.count())
                .select_from(Membership)
                .where(
                    Membership.organization_id == organization_id,
                    Membership.role == MembershipRole.admin,
                )
            )
            or 0
        )
        if admins <= 1:
            raise AppError(
                409,
                "last_admin",
                "The last organization administrator cannot be removed",
            )
    db.delete(membership)


def create_password_reset(db: Session, email: str) -> str | None:
    user = db.scalar(select(User).where(User.email == normalize_email(email)).with_for_update())
    if user is None or not user.is_active:
        return None
    now = datetime.now(UTC)
    recent = db.scalar(
        select(PasswordResetToken.id)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.created_at > now - timedelta(minutes=1),
        )
        .limit(1)
    )
    if recent is not None:
        return None
    token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=now + timedelta(hours=1),
        )
    )
    db.commit()
    return token


def reset_password(db: Session, token: str, password: str) -> User:
    digest = hashlib.sha256(token.encode()).hexdigest()
    user_id = db.scalar(
        select(PasswordResetToken.user_id).where(PasswordResetToken.token_hash == digest)
    )
    user = db.scalar(select(User).where(User.id == user_id).with_for_update()) if user_id else None
    row = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == digest).with_for_update()
    )
    now = datetime.now(UTC)
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise AppError(400, "invalid_reset_token", "This reset link is invalid or expired")
    if user is None or not user.is_active:
        raise AppError(400, "invalid_reset_token", "This reset link is invalid or expired")
    user.password_hash = hash_password(password)
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    db.query(UserSession).filter(UserSession.user_id == user.id).update(
        {UserSession.revoked_at: now}, synchronize_session=False
    )
    db.commit()
    db.refresh(user)
    return user


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
