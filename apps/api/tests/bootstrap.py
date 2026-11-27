"""Test bootstrap. Sets settings to the test database before the app is imported."""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text

from tests.smtp_sink import start_process_sink

REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = Path(__file__).resolve().parents[1]

if not (REPO_ROOT / "compose.yaml").is_file():
    raise RuntimeError(f"Unexpected repository root: {REPO_ROOT}")


def _load_postgres_defaults() -> None:
    env_file = REPO_ROOT / ".env"
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("POSTGRES_") and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def postgres_url(database: str) -> str:
    user = quote_plus(os.environ.get("POSTGRES_USER", "atlas"))
    password = quote_plus(os.environ.get("POSTGRES_PASSWORD", "atlas"))
    # Use IPv4 explicitly for disposable Windows/Docker runs. ``localhost`` can
    # resolve to an unreachable IPv6 listener before trying the mapped port.
    host = os.environ.get("ATLAS_E2E_POSTGRES_HOST") or os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"


_load_postgres_defaults()

def test_database_name() -> str:
    requested = os.environ.get("ATLAS_TEST_DATABASE", "atlas_test").strip()
    if requested == "atlas_test" or re.fullmatch(r"atlas_rehearsal_[a-z0-9_]{1,40}", requested):
        return requested
    raise RuntimeError(f"Refusing unexpected test database {requested}")


TEST_DATABASE_NAME = test_database_name()
TEST_DATABASE_URL = postgres_url(TEST_DATABASE_NAME)
MIGRATION_DATABASE_URL = postgres_url("atlas_migration_test")
ADMIN_DATABASE_URL = postgres_url("postgres")

os.environ["ATLAS_ENVIRONMENT"] = "test"
os.environ["ATLAS_PUBLIC_DEMO"] = "false"
os.environ["ATLAS_LLM_PROVIDER"] = "openai"
os.environ["ATLAS_LLM_BASE_URL"] = "https://api.openai.com/v1"
os.environ["ATLAS_LLM_API_KEY"] = ""
os.environ["ATLAS_LLM_MODEL"] = "gpt-4o-mini"
os.environ["ATLAS_EMBEDDING_PROVIDER"] = "openai"
os.environ["ATLAS_EMBEDDING_BASE_URL"] = "https://api.openai.com/v1"
os.environ["ATLAS_EMBEDDING_API_KEY"] = ""
os.environ["ATLAS_EMBEDDING_MODEL"] = "text-embedding-3-small"
os.environ["ATLAS_EMBEDDING_DIMENSIONS"] = "1536"
os.environ["ATLAS_SECRET_KEY"] = "test-secret-key-must-be-32-chars-min"
os.environ["ATLAS_DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ATLAS_CORS_ORIGINS"] = "http://127.0.0.1:3000,http://localhost:3000"
os.environ["ATLAS_COOKIE_SECURE"] = "false"
os.environ["ATLAS_LOG_LEVEL"] = "WARNING"

_smtp_sink = start_process_sink()
os.environ["ATLAS_SMTP_HOST"] = "127.0.0.1"
os.environ["ATLAS_SMTP_PORT"] = str(_smtp_sink.port)
os.environ["ATLAS_EMAIL_MODE"] = "sandbox"
os.environ["ATLAS_N8N_LEAD_WEBHOOK_URL"] = ""


def ensure_database(name: str, *, require_new: bool = False) -> None:
    rehearsal = re.fullmatch(r"atlas_rehearsal_[a-z0-9_]{1,40}", name) is not None
    generated = require_new and re.fullmatch(r"atlas_e2e_[0-9a-f]{32}", name) is not None
    if name not in {"atlas_test", "atlas_migration_test"} and not rehearsal and not generated:
        raise RuntimeError(f"Refusing to create unexpected database {name}")
    admin = create_engine(
        ADMIN_DATABASE_URL,
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 5,
            "options": "-c lock_timeout=5000 -c statement_timeout=30000",
        },
    )
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": name},
            ).scalar()
            if exists == 1 and require_new:
                raise RuntimeError("The generated browser database already exists.")
            if exists != 1:
                connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()


def drop_generated_database(name: str) -> None:
    """Drop one browser database. The name must be a generated acceptance id."""

    if re.fullmatch(r"atlas_e2e_[0-9a-f]{32}", name) is None:
        raise RuntimeError("Refusing to drop an unexpected database")
    admin = create_engine(
        ADMIN_DATABASE_URL,
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 5,
            "options": "-c lock_timeout=5000 -c statement_timeout=30000",
        },
    )
    try:
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    finally:
        admin.dispose()
