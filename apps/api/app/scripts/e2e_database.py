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
    from sqlalchemy import func, select, text

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
        db.execute(
            text(
                "TRUNCATE TABLE message_sources, messages, conversations, chunks, documents, "
                "lead_predictions, evaluation_runs, operation_traces, model_versions, "
                "email_messages, calendar_bookings, execution_attempts, execution_intents, "
                "workflow_runs, webhook_events, webhook_keys, integration_configs, "
                "agent_events, approvals, agent_runs, audit_events, interactions, inquiries, "
                "leads, contacts, companies, sessions, memberships, users, organizations "
                "RESTART IDENTITY CASCADE"
            )
        )
        db.commit()
        seed_identity(db, SeedSettings())
        atlas = db.scalar(select(Organization).where(Organization.slug == "northwind"))
        admin = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert atlas is not None and admin is not None
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
