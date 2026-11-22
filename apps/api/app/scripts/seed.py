"""Idempotent synthetic identity seed.

Running this again updates the same users, organizations, and memberships in place.
It also resets those users' passwords to the current seed values. Do not run it in production.
"""

from __future__ import annotations

import sys
from typing import Self

from pydantic import EmailStr, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.orm import Session

from app.core.config import ENV_FILE, get_settings
from app.core.database import SessionLocal
from app.core.logging import configure_logging
from app.domains.crm.sample_data import seed_sample_crm
from app.domains.identity.models import MembershipRole
from app.domains.identity.service import upsert_membership, upsert_organization, upsert_user


class SeedSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE if ENV_FILE is not None and ENV_FILE.is_file() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    seed_admin_email: EmailStr
    seed_admin_password: str = Field(min_length=8, max_length=128)
    seed_admin_name: str = Field(min_length=1, max_length=200)
    seed_staff_email: EmailStr
    seed_staff_password: str = Field(min_length=8, max_length=128)
    seed_staff_name: str = Field(min_length=1, max_length=200)
    seed_outsider_email: EmailStr
    seed_outsider_password: str = Field(min_length=8, max_length=128)
    seed_outsider_name: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def emails_must_be_distinct(self) -> Self:
        emails = {
            str(self.seed_admin_email).lower(),
            str(self.seed_staff_email).lower(),
            str(self.seed_outsider_email).lower(),
        }
        if len(emails) != 3:
            raise ValueError(
                "SEED_ADMIN_EMAIL, SEED_STAFF_EMAIL, and SEED_OUTSIDER_EMAIL must differ"
            )
        return self


def seed_identity(db: Session, settings: SeedSettings) -> None:
    atlas = upsert_organization(db, name="Atlas Demo", slug="atlas-demo")
    northwind = upsert_organization(db, name="Northwind", slug="northwind")
    admin = upsert_user(
        db,
        email=str(settings.seed_admin_email),
        full_name=settings.seed_admin_name,
        password=settings.seed_admin_password,
    )
    staff = upsert_user(
        db,
        email=str(settings.seed_staff_email),
        full_name=settings.seed_staff_name,
        password=settings.seed_staff_password,
    )
    outsider = upsert_user(
        db,
        email=str(settings.seed_outsider_email),
        full_name=settings.seed_outsider_name,
        password=settings.seed_outsider_password,
    )
    upsert_membership(db, user=admin, organization=atlas, role=MembershipRole.admin)
    upsert_membership(db, user=staff, organization=atlas, role=MembershipRole.staff)
    upsert_membership(db, user=outsider, organization=northwind, role=MembershipRole.admin)
    seed_sample_crm(db, atlas=atlas, northwind=northwind, admin=admin, outsider=outsider)
    db.commit()


def main() -> int:
    app_settings = get_settings()
    if app_settings.environment == "production":
        print("Refusing to seed while ATLAS_ENVIRONMENT=production.", file=sys.stderr)
        return 1
    configure_logging(app_settings.log_level, app_settings.environment)
    seed_settings = SeedSettings()
    db = SessionLocal()
    try:
        seed_identity(db, seed_settings)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print("Seed complete. Passwords were not printed.")
    print(
        "- Atlas Demo (atlas-demo): "
        f"{seed_settings.seed_admin_email} (admin), "
        f"{seed_settings.seed_staff_email} (staff)"
    )
    print(f"- Northwind (northwind): {seed_settings.seed_outsider_email} (admin)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
