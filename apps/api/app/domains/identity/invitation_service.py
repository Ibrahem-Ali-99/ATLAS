import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.domains.audit.service import record_event
from app.domains.identity.invitation_models import InvitationRole, OrganizationInvitation
from app.domains.identity.models import Membership, MembershipRole, Organization, User
from app.domains.identity.service import normalize_email

INVITATION_TTL = timedelta(days=7)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_invitation(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, email: str
) -> tuple[OrganizationInvitation, str]:
    normalized = normalize_email(email)
    existing = db.scalar(select(User).where(User.email == normalized).with_for_update())
    if (
        existing is not None
        and db.scalar(
            select(Membership).where(
                Membership.user_id == existing.id, Membership.organization_id == organization_id
            )
        )
        is not None
    ):
        raise AppError(409, "already_member", "This user is already a member of the organization")
    now = datetime.now(UTC)
    db.query(OrganizationInvitation).filter(
        OrganizationInvitation.organization_id == organization_id,
        OrganizationInvitation.email == normalized,
        OrganizationInvitation.accepted_at.is_(None),
    ).update({OrganizationInvitation.accepted_at: now}, synchronize_session=False)
    token = secrets.token_urlsafe(32)
    invitation = OrganizationInvitation(
        organization_id=organization_id,
        invited_by=actor_id,
        email=normalized,
        role=InvitationRole.staff,
        token_hash=_hash_token(token),
        expires_at=now + INVITATION_TTL,
    )
    db.add(invitation)
    record_event(
        db,
        organization_id,
        "organization_invitation_created",
        {"email": normalized},
        actor_id=actor_id,
    )
    db.commit()
    db.refresh(invitation)
    return invitation, token


def resend_invitation(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, invitation_id: uuid.UUID
) -> tuple[OrganizationInvitation, str]:
    invitation = db.scalar(
        select(OrganizationInvitation)
        .where(
            OrganizationInvitation.id == invitation_id,
            OrganizationInvitation.organization_id == organization_id,
        )
        .with_for_update()
    )
    if invitation is None:
        raise AppError(404, "invitation_not_found", "Invitation not found")
    if invitation.accepted_at is not None:
        raise AppError(409, "invitation_closed", "This invitation has already been accepted")
    existing = db.scalar(select(User).where(User.email == invitation.email))
    if (
        existing is not None
        and db.scalar(
            select(Membership).where(
                Membership.user_id == existing.id, Membership.organization_id == organization_id
            )
        )
        is not None
    ):
        raise AppError(409, "already_member", "This user is already a member of the organization")
    token = secrets.token_urlsafe(32)
    invitation.token_hash = _hash_token(token)
    invitation.expires_at = datetime.now(UTC) + INVITATION_TTL
    record_event(
        db,
        organization_id,
        "organization_invitation_resent",
        {"invitation_id": str(invitation.id)},
        actor_id=actor_id,
    )
    db.commit()
    db.refresh(invitation)
    return invitation, token


def accept_invitation(
    db: Session, token: str, *, full_name: str, password: str
) -> tuple[User, Organization]:
    if not token.strip():
        raise AppError(400, "invalid_invitation", "This invitation is invalid or expired")
    invitation = db.scalar(
        select(OrganizationInvitation)
        .where(OrganizationInvitation.token_hash == _hash_token(token))
        .with_for_update()
    )
    now = datetime.now(UTC)
    if invitation is None or invitation.accepted_at is not None or invitation.expires_at <= now:
        raise AppError(400, "invalid_invitation", "This invitation is invalid or expired")
    user = db.scalar(select(User).where(User.email == invitation.email).with_for_update())
    if user is None:
        user = User(
            email=invitation.email,
            full_name=full_name.strip(),
            password_hash=hash_password(password),
            is_active=True,
        )
        db.add(user)
        db.flush()
    elif not user.is_active:
        raise AppError(403, "inactive_account", "This account cannot accept an invitation")
    elif not verify_password(password, user.password_hash):
        raise AppError(
            403,
            "invitation_account_mismatch",
            "Sign in with the invited account password",
        )
    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id, Membership.organization_id == invitation.organization_id
        )
    )
    if membership is not None:
        raise AppError(409, "already_member", "This user is already a member of the organization")
    db.add(
        Membership(
            user_id=user.id, organization_id=invitation.organization_id, role=MembershipRole.staff
        )
    )
    invitation.accepted_at = now
    organization = db.get(Organization, invitation.organization_id)
    if organization is None:
        raise AppError(400, "invalid_invitation", "This invitation is invalid or expired")
    record_event(db, organization.id, "organization_invitation_accepted", {"user_id": str(user.id)})
    db.commit()
    db.refresh(user)
    return user, organization
