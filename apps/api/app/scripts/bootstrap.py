"""Create the first organization and administrator.

This is the production initialization path. It does not load demonstration CRM
rows and it does not change an account that already exists. Credentials are
read from stdin or from ATLAS_BOOTSTRAP_* variables supplied for this process
only. The result line never includes the password.
"""

from __future__ import annotations

import json
import sys
from typing import Self

from pydantic import BaseModel, EmailStr, Field, ValidationError, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.domains.crm.models import Company
from app.domains.identity.models import Membership, MembershipRole, Organization, User
from app.domains.identity.service import normalize_email

_WEAK_MARKERS = ("replace-with", "change-me", "changeme", "dev-only", "password")


class BootstrapRefused(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class BootstrapRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=200)
    organization_slug: str = Field(
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=1, max_length=80
    )
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def password_is_not_a_placeholder(cls, value: str) -> str:
        lowered = value.lower()
        if any(marker in lowered for marker in _WEAK_MARKERS):
            raise ValueError("weak_password")
        return value

    @model_validator(mode="after")
    def strip_names(self) -> Self:
        self.organization_name = self.organization_name.strip()
        self.full_name = self.full_name.strip()
        if not self.organization_name or not self.full_name:
            raise ValueError("invalid_input")
        return self


def read_request(stdin_text: str | None, env: dict[str, str]) -> BootstrapRequest:
    raw = (stdin_text or "").strip()
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BootstrapRefused("invalid_input") from exc
        if not isinstance(payload, dict):
            raise BootstrapRefused("invalid_input")
        values = payload
    else:
        values = {
            "organization_name": env.get("ATLAS_BOOTSTRAP_ORGANIZATION_NAME", ""),
            "organization_slug": env.get("ATLAS_BOOTSTRAP_ORGANIZATION_SLUG", ""),
            "email": env.get("ATLAS_BOOTSTRAP_EMAIL", ""),
            "full_name": env.get("ATLAS_BOOTSTRAP_FULL_NAME", ""),
            "password": env.get("ATLAS_BOOTSTRAP_PASSWORD", ""),
        }
    try:
        return BootstrapRequest.model_validate(values)
    except ValidationError as exc:
        if any("weak_password" in error["msg"] for error in exc.errors()):
            raise BootstrapRefused("weak_password") from None
        raise BootstrapRefused("invalid_input") from None


def create_first_administrator(db: Session, request: BootstrapRequest) -> tuple[Organization, User]:
    settings = get_settings()
    if settings.public_demo:
        raise BootstrapRefused("public_demo")
    administrator = db.scalar(
        select(Membership.id).where(Membership.role == MembershipRole.admin).limit(1)
    )
    if administrator is not None:
        raise BootstrapRefused("administrator_exists")
    if db.scalar(select(User.id).limit(1)) is not None:
        raise BootstrapRefused("already_initialized")
    if db.scalar(select(Organization.id).limit(1)) is not None:
        raise BootstrapRefused("already_initialized")
    organization = Organization(name=request.organization_name, slug=request.organization_slug)
    user = User(
        email=normalize_email(str(request.email)),
        full_name=request.full_name,
        password_hash=hash_password(request.password),
        is_active=True,
    )
    db.add(organization)
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise BootstrapRefused("already_initialized") from exc
    db.add(
        Membership(
            user_id=user.id,
            organization_id=organization.id,
            role=MembershipRole.admin,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BootstrapRefused("already_initialized") from exc
    db.refresh(organization)
    db.refresh(user)
    return organization, user


def status_line(db: Session) -> str:
    users = db.scalar(select(func.count()).select_from(User)) or 0
    organizations = db.scalar(select(func.count()).select_from(Organization)) or 0
    administrators = (
        db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.role == MembershipRole.admin)
        )
        or 0
    )
    companies = db.scalar(select(func.count()).select_from(Company)) or 0
    return (
        "bootstrap_status "
        f"users={users} organizations={organizations} "
        f"administrators={administrators} companies={companies}"
    )


def main(stdin_text: str | None = None, env: dict[str, str] | None = None) -> int:
    if "--status" in sys.argv:
        db = SessionLocal()
        try:
            print(status_line(db))
        finally:
            db.close()
        return 0
    source = sys.stdin.read() if stdin_text is None else stdin_text
    try:
        request = read_request(source, os_environ() if env is None else env)
    except BootstrapRefused as exc:
        print(f"bootstrap_refused reason={exc.reason}")
        return 2
    db = SessionLocal()
    try:
        organization, user = create_first_administrator(db, request)
    except BootstrapRefused as exc:
        print(f"bootstrap_refused reason={exc.reason}")
        return 2
    except Exception as exc:
        db.rollback()
        print(f"bootstrap_failed error={type(exc).__name__}")
        return 1
    finally:
        db.close()
    print(
        f"bootstrap_ok organization_id={organization.id} user_id={user.id} slug={organization.slug}"
    )
    return 0


def os_environ() -> dict[str, str]:
    import os

    return dict(os.environ)


if __name__ == "__main__":
    raise SystemExit(main())
