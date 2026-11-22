"""Create the isolated atlas_e2e database used by the browser test.

Does not print the database URL or seed passwords.
"""

from __future__ import annotations

import os


def main() -> None:
    from tests.bootstrap import ensure_database, postgres_url

    ensure_database("atlas_e2e")
    url = postgres_url("atlas_e2e")
    os.environ["ALEMBIC_DATABASE_URL"] = url
    os.environ["ATLAS_DATABASE_URL"] = url
    os.environ["ATLAS_ENVIRONMENT"] = "development"

    from alembic.config import Config

    from alembic import command
    from app.core.config import get_settings
    from app.core.database import SessionLocal
    from app.scripts.seed import SeedSettings, seed_identity

    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    get_settings.cache_clear()
    db = SessionLocal()
    try:
        seed_identity(db, SeedSettings())
    finally:
        db.close()
    print("e2e database ready")


if __name__ == "__main__":
    main()
