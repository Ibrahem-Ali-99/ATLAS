from __future__ import annotations

import os

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from tests.bootstrap import API_ROOT, TEST_DATABASE_URL, ensure_database

os.environ["ALEMBIC_DATABASE_URL"] = TEST_DATABASE_URL


def _alembic_config(url: str) -> Config:
    os.environ["ALEMBIC_DATABASE_URL"] = url
    return Config(str(API_ROOT / "alembic.ini"))


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    ensure_database("atlas_test")
    ensure_database("atlas_migration_test")
    command.upgrade(_alembic_config(TEST_DATABASE_URL), "head")


@pytest.fixture(autouse=True)
def clean_tables() -> None:
    from app.core.config import get_settings
    from app.core.database import engine

    url = get_settings().database_url
    if not url.endswith("/atlas_test"):
        raise RuntimeError(f"Refusing to truncate unexpected database: {url}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE message_sources, messages, conversations, chunks, documents, "
                "ingestion_jobs, "
                "lead_predictions, evaluation_runs, operation_traces, model_versions, "
                "email_messages, calendar_bookings, execution_attempts, execution_intents, "
                "workflow_runs, webhook_events, webhook_keys, integration_configs, "
                "agent_events, approvals, agent_runs, audit_events, "
                "interactions, inquiries, leads, contacts, companies, "
                "organization_invitations, sessions, memberships, users, organizations "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def db() -> Session:
    from app.core.database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> TestClient:
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
