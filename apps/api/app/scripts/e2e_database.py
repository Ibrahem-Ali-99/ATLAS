"""Create and seed a fresh database for one browser acceptance run.

Does not print the database URL or seed passwords.
"""

from __future__ import annotations

import os
import re


def database_name() -> str:
    name = os.environ.get("ATLAS_E2E_DATABASE_NAME", "")
    if not re.fullmatch(r"atlas_e2e_[0-9a-f]{32}", name):
        raise RuntimeError("The browser runner must provide a generated acceptance database name.")
    return name


def main() -> None:
    from tests.bootstrap import ensure_database, postgres_url

    name = database_name()
    ensure_database(name, require_new=True)
    url = postgres_url(name)
    os.environ["ALEMBIC_DATABASE_URL"] = url
    os.environ["ATLAS_DATABASE_URL"] = url
    os.environ["ATLAS_ENVIRONMENT"] = "development"

    from alembic.config import Config
    from sqlalchemy import func, select

    from alembic import command
    from app.core.config import get_settings
    from app.core.database import SessionLocal
    from app.domains.identity.models import Organization, User
    from app.domains.integrations.models import IntegrationConfig
    from app.domains.knowledge.models import Chunk, Document, DocumentStatus
    from app.domains.provenance.origin import Origin
    from app.scripts.seed import SeedSettings, seed_identity

    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    get_settings.cache_clear()
    db = SessionLocal()
    try:
        seed_settings = SeedSettings()
        seed_identity(db, seed_settings)
        atlas = db.scalar(select(Organization).where(Organization.slug == "northwind"))
        admin = db.scalar(
            select(User).where(User.email == str(seed_settings.seed_admin_email).lower())
        )
        if atlas is None or admin is None:
            organization_slugs = list(
                db.scalars(select(Organization.slug).order_by(Organization.slug))
            )
            user_emails = list(db.scalars(select(User.email).order_by(User.email)))
            raise RuntimeError(
                "Disposable identity seed did not create the required fixture: "
                f"northwind_present={atlas is not None}, "
                f"admin_email_present={admin is not None}, "
                f"expected_admin={seed_settings.seed_admin_email}, "
                f"organizations={organization_slugs}, users={user_emails}"
            )
        fixture = db.scalar(
            select(Document).where(
                Document.organization_id == atlas.id,
                Document.title == "E2E Embedding Compatibility Fixture",
            )
        )
        if fixture is None:
            fixture = Document(
                organization_id=atlas.id,
                uploaded_by=admin.id,
                title="E2E Embedding Compatibility Fixture",
                filename="e2e-embedding-fixture.txt",
                media_type="text/plain",
                byte_size=77,
                storage_path="",
                status=DocumentStatus.ready,
                origin=Origin.demo,
            )
            db.add(fixture)
            db.flush()
            chunk = Chunk(
                organization_id=atlas.id,
                document_id=fixture.id,
                chunk_index=0,
                content="Disposable fixture for embedding compatibility acceptance.",
                search_vector=func.to_tsvector(
                    "english", "Disposable fixture for embedding compatibility acceptance."
                ),
                embedding_768=[0.0] * 768,
                embedding_model="nomic-embed-text:v1.5",
            )
            db.add(chunk)
        db.add(
            IntegrationConfig(
                organization_id=atlas.id,
                integration_type="embedding",
                provider="ollama",
                config={
                    "base_url": "http://ollama:11434/v1",
                    "model": "nomic-embed-text:v1.5",
                    "dimensions": 768,
                },
            )
        )
        db.commit()
    finally:
        db.close()
    print("e2e database ready")


if __name__ == "__main__":
    main()
