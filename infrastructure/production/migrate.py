"""Plan a schema change. This command does not connect to a database.

The API container applies `alembic upgrade head` before it serves traffic.
Roll back one revision only after a backup, and only when this check says the
current head is reversible. A step marked manual_downgrade leaves database
objects behind; restore the backup instead of walking through that revision.
"""

from __future__ import annotations

import argparse

from migration_contract import inspect_tree


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate the revision chain and exit")
    parser.add_argument("--plan", action="store_true", help="Print the upgrade and rollback procedure")
    args = parser.parse_args()
    if args.check == args.plan:
        parser.error("choose either --check or --plan")
    report = inspect_tree()
    if not report.ok:
        for problem in report.problems:
            print(f"Blocked: {problem}")
        return 2
    manual = set(report.irreversible)
    if args.check:
        names = ",".join(report.irreversible) if report.irreversible else "none"
        print(
            f"migration_ok head={report.head} revisions={report.revisions} "
            f"manual_downgrade={names}"
        )
        return 0
    print("1. Run infrastructure/production/backup.py and confirm backup_ok.")
    print("2. Keep the backup passphrase and production env file outside the archive.")
    print("3. Start or recreate the API container. Its entrypoint runs alembic upgrade head.")
    print("4. Confirm /api/v1/ready and the head revision inside the API container:")
    print("     alembic current")
    if report.head in manual:
        print(f"5. Head {report.head} is not a safe one-step downgrade. Restore the backup.")
    else:
        print("5. To undo one reversible step, stop traffic and run this once inside the API container:")
        print("     alembic downgrade -1")
        print("   Then recreate the container only after checking the data. A second API process")
        print("   would apply upgrade head again as soon as it starts.")
    if manual:
        print("Manual downgrades that must use a backup instead of alembic downgrade:")
        for revision in report.irreversible:
            print(f"  - {revision}")
    print("Do not run this against the development database or a shared running project.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
