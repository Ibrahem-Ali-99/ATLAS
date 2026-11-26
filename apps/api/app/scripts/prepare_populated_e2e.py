"""Manage a synthetic workspace in the disposable browser database."""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.errors import AppError


def _guard() -> None:
    from app.scripts.e2e_database import database_name

    database_url = os.environ.get("ATLAS_DATABASE_URL", "")
    if make_url(database_url).database != database_name():
        raise AppError(400, "unsafe_database", "Use the generated browser database.")


def sample_workspace(
    db: Session, slug: str, *, verify: bool = False, cleanup: bool = False
) -> dict[str, object]:
    from app.domains.assistant.models import Conversation
    from app.domains.crm.models import Company, Contact, Inquiry, Interaction, Lead
    from app.domains.identity.models import MembershipRole, Organization, User
    from app.domains.identity.service import upsert_membership, upsert_organization
    from app.scripts.populate_workspace import populate, purge
    from app.scripts.seed import SeedSettings

    _guard()
    if not slug.startswith("sample-"):
        raise AppError(400, "unsafe_organization", "Use a sample workspace slug.")
    organization = db.scalar(select(Organization).where(Organization.slug == slug))
    if cleanup:
        if organization is not None:
            purge(db, organization)
            db.execute(delete(Organization).where(Organization.id == organization.id))
            db.commit()
        return {"status": "removed"}
    if verify:
        if organization is None:
            raise AppError(404, "organization_missing", "The sample organization is missing.")
        expected = (
            (Company, 3),
            (Contact, 3),
            (Lead, 5),
            (Inquiry, 3),
            (Interaction, 3),
            (Conversation, 1),
        )
        for model, expected_count in expected:
            count = db.scalar(
                select(func.count())
                .select_from(model)
                .where(model.organization_id == organization.id)
            )
            if count != expected_count:
                raise AppError(409, "unexpected_counts", "The sample workspace is incomplete.")
        return {"status": "verified"}
    if organization is None:
        organization = upsert_organization(db, name="ATLAS Sample Workspace", slug=slug)
    seed_settings = SeedSettings()
    admin = db.scalar(select(User).where(User.email == str(seed_settings.seed_admin_email).lower()))
    if admin is None:
        raise AppError(422, "e2e_admin_missing", "The disposable administrator is missing.")
    upsert_membership(db, user=admin, organization=organization, role=MembershipRole.admin)
    populate(db, organization)
    db.commit()
    return {"status": "populated"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization-slug", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--cleanup", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    from app.scripts.e2e_database import database_name
    from tests.bootstrap import postgres_url

    os.environ["ATLAS_DATABASE_URL"] = postgres_url(database_name())
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.core.database import SessionLocal

    try:
        with SessionLocal() as db:
            result = sample_workspace(
                db, args.organization_slug, verify=args.verify, cleanup=args.cleanup
            )
        print(f"e2e_population_{result['status']} slug={args.organization_slug}")
        return 0
    except Exception as exc:
        print(f"e2e_population_failed {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
