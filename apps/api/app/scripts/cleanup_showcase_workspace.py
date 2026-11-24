"""Remove seeded display markers from the explicitly designated showcase workspace.

Dry-run is the default. Applying or rolling back requires an explicit confirmation.
This script never searches or updates records outside ``sample-atlas-showcase``.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.database import SessionLocal
from app.domains.assistant.models import Conversation
from app.domains.crm.models import Company, Contact, Inquiry, Interaction, Lead
from app.domains.identity.models import Organization

SLUG = "sample-atlas-showcase"
MARKER = "Sample workspace · "
DISPLAY_NAME = "Northstar Studio"
FIELDS: tuple[tuple[type[Any], str], ...] = (
    (Company, "name"),
    (Contact, "full_name"),
    (Lead, "title"),
    (Inquiry, "subject"),
    (Interaction, "body"),
    (Conversation, "title"),
)


def _organization(db: Any) -> Organization:
    organization = db.scalar(select(Organization).where(Organization.slug == SLUG))
    if organization is None:
        raise ValueError(f"required showcase organization {SLUG!r} was not found")
    return organization


def _changes(db: Any, organization: Organization) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    for model, field in FIELDS:
        rows = db.scalars(select(model).where(model.organization_id == organization.id)).all()
        for row in rows:
            value = getattr(row, field)
            if isinstance(value, str) and value.startswith(MARKER):
                changes.append(
                    {
                        "table": model.__tablename__,
                        "id": str(row.id),
                        "field": field,
                        "old": value,
                        "new": value.removeprefix(MARKER),
                    }
                )
    if organization.name != DISPLAY_NAME:
        changes.append(
            {
                "table": Organization.__tablename__,
                "id": str(organization.id),
                "field": "name",
                "old": organization.name,
                "new": DISPLAY_NAME,
            }
        )
    return changes


def _apply(db: Any, organization: Organization, changes: list[dict[str, str]]) -> None:
    models = {model.__tablename__: model for model, _ in FIELDS} | {
        Organization.__tablename__: Organization
    }
    for change in changes:
        row = db.get(models[change["table"]], change["id"])
        if row is None or getattr(row, change["field"]) != change["old"]:
            raise ValueError(
                f"showcase cleanup changed before apply: {change['table']}:{change['id']}"
            )
        setattr(row, change["field"], change["new"])


def _rollback(db: Any, changes: list[dict[str, str]]) -> None:
    models = {model.__tablename__: model for model, _ in FIELDS} | {
        Organization.__tablename__: Organization
    }
    for change in changes:
        row = db.get(models[change["table"]], change["id"])
        if row is None or getattr(row, change["field"]) != change["new"]:
            raise ValueError(
                f"showcase rollback changed before restore: {change['table']}:{change['id']}"
            )
        setattr(row, change["field"], change["old"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Clean only the sample-atlas-showcase display labels."
    )
    parser.add_argument("--apply", action="store_true", help="persist the reviewed cleanup")
    parser.add_argument("--rollback", type=Path, help="restore a rollback file produced by --apply")
    parser.add_argument("--confirm-showcase-cleanup", action="store_true")
    parser.add_argument(
        "--rollback-file", type=Path, default=Path("showcase-cleanup-rollback.json")
    )
    args = parser.parse_args(argv)
    if (args.apply or args.rollback) and not args.confirm_showcase_cleanup:
        parser.error("--confirm-showcase-cleanup is required for writes")
    db = SessionLocal()
    try:
        organization = _organization(db)
        if args.rollback:
            changes = json.loads(args.rollback.read_text(encoding="utf-8"))
            _rollback(db, changes)
            db.commit()
            print(f"showcase_cleanup_ok mode=rollback organization={SLUG} changes={len(changes)}")
            return 0
        changes = _changes(db, organization)
        print(f"showcase_cleanup_review organization={SLUG} changes={len(changes)}")
        if not args.apply:
            return 0
        args.rollback_file.write_text(json.dumps(changes, indent=2) + "\n", encoding="utf-8")
        _apply(db, organization, changes)
        db.commit()
        print(
            f"showcase_cleanup_ok mode=apply organization={SLUG} "
            f"changes={len(changes)} rollback={args.rollback_file}"
        )
        return 0
    except Exception as exc:
        db.rollback()
        print(f"showcase_cleanup_failed {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
