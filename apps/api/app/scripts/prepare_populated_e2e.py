"""Create and remove a disposable populated workspace for browser acceptance."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from sqlalchemy import delete, func, select

from app.core.errors import AppError
from app.domains.identity.models import MembershipRole, Organization, User
from app.domains.identity.service import upsert_membership, upsert_organization


def _guard() -> None:
    if os.environ.get("ATLAS_E2E_PRODUCTION") != "1":
        raise AppError(
            400, "e2e_only", "This helper is restricted to the disposable E2E environment."
        )
    database_url = os.environ.get("ATLAS_DATABASE_URL", "")
    if "atlas_e2e" not in database_url:
        raise AppError(400, "unsafe_database", "This helper requires the atlas_e2e database.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization-slug", required=True)
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    from tests.bootstrap import postgres_url

    os.environ["ATLAS_DATABASE_URL"] = postgres_url("atlas_e2e")
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        _guard()
        organization = db.scalar(
            select(Organization).where(Organization.slug == args.organization_slug)
        )
        if args.cleanup:
            if organization is not None:
                db.commit()
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "app.scripts.populate_workspace",
                        "--organization-slug",
                        args.organization_slug,
                        "--confirm-sample-workspace",
                        "--purge",
                    ],
                    check=False,
                )
                if result.returncode != 0:
                    raise AppError(500, "cleanup_failed", "The sample purge command failed.")
                db.expire_all()
                db.execute(delete(Organization).where(Organization.id == organization.id))
        elif args.verify:
            if organization is None:
                raise AppError(404, "organization_missing", "The sample organization is missing.")
            from app.domains.assistant.models import Conversation
            from app.domains.crm.models import Company, Contact, Inquiry, Interaction, Lead

            counts = {
                "companies": db.scalar(
                    select(func.count())
                    .select_from(Company)
                    .where(Company.organization_id == organization.id)
                ),
                "contacts": db.scalar(
                    select(func.count())
                    .select_from(Contact)
                    .where(Contact.organization_id == organization.id)
                ),
                "leads": db.scalar(
                    select(func.count())
                    .select_from(Lead)
                    .where(Lead.organization_id == organization.id)
                ),
                "inquiries": db.scalar(
                    select(func.count())
                    .select_from(Inquiry)
                    .where(Inquiry.organization_id == organization.id)
                ),
                "interactions": db.scalar(
                    select(func.count())
                    .select_from(Interaction)
                    .where(Interaction.organization_id == organization.id)
                ),
                "conversations": db.scalar(
                    select(func.count())
                    .select_from(Conversation)
                    .where(Conversation.organization_id == organization.id)
                ),
            }
            expected = {
                "companies": 3,
                "contacts": 3,
                "leads": 5,
                "inquiries": 3,
                "interactions": 3,
                "conversations": 1,
            }
            if counts != expected:
                raise AppError(409, "unexpected_counts", f"Expected {expected}, found {counts}.")
            print(f"e2e_population_verify_ok slug={args.organization_slug} counts={counts}")
            return 0
        else:
            if organization is None:
                organization = upsert_organization(
                    db, name="ATLAS Sample Workspace", slug=args.organization_slug
                )
            admin = db.scalar(select(User).where(User.email == "admin@example.com"))
            if admin is None:
                raise AppError(422, "e2e_admin_missing", "The disposable admin fixture is missing.")
            upsert_membership(db, user=admin, organization=organization, role=MembershipRole.admin)
            db.commit()
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app.scripts.populate_workspace",
                    "--organization-slug",
                    args.organization_slug,
                    "--confirm-sample-workspace",
                ],
                check=False,
            )
            if result.returncode != 0:
                raise AppError(500, "population_failed", "The sample population command failed.")
            print(f"e2e_population_ok slug={args.organization_slug}")
            return 0
        db.commit()
        print(f"e2e_population_cleanup_ok slug={args.organization_slug}")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"e2e_population_failed {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
