from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.domains.identity.models import Membership, MembershipRole, Organization, User

PASSWORD = "correct-horse-1"


def make_user(
    db: Session,
    email: str,
    password: str = PASSWORD,
    *,
    full_name: str = "Test User",
    is_active: bool = True,
) -> User:
    user = User(
        email=email.lower(),
        full_name=full_name,
        password_hash=hash_password(password),
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_organization(db: Session, name: str, slug: str) -> Organization:
    organization = Organization(name=name, slug=slug)
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


def make_membership(
    db: Session,
    user: User,
    organization: Organization,
    role: MembershipRole,
) -> Membership:
    membership = Membership(user_id=user.id, organization_id=organization.id, role=role)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership
