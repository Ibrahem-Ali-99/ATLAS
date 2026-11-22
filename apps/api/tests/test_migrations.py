import os

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from tests.bootstrap import API_ROOT, MIGRATION_DATABASE_URL, ensure_database


def _config() -> Config:
    os.environ["ALEMBIC_DATABASE_URL"] = MIGRATION_DATABASE_URL
    return Config(str(API_ROOT / "alembic.ini"))


def test_origin_migration_leaves_existing_rows_unknown() -> None:
    ensure_database("atlas_migration_test")
    engine = create_engine(MIGRATION_DATABASE_URL, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    config = _config()
    command.upgrade(config, "20261122_0010")
    engine = create_engine(MIGRATION_DATABASE_URL, pool_pre_ping=True)
    user_id = "00000000-0000-4000-8000-000000000011"
    org_id = "00000000-0000-4000-8000-000000000012"
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO users (id, email, full_name, password_hash)
                VALUES (:id, 'legacy@example.com', 'Legacy', 'hash')
                """
            ),
            {"id": user_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO organizations (id, name, slug)
                VALUES (:id, 'Legacy Org', 'legacy-org')
                """
            ),
            {"id": org_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO leads (organization_id, owner_user_id, title, status)
                VALUES (:org, :owner, 'Historical lead', 'new')
                """
            ),
            {"org": org_id, "owner": user_id},
        )
    engine.dispose()
    command.upgrade(config, "head")
    engine = create_engine(MIGRATION_DATABASE_URL, pool_pre_ping=True)
    with engine.connect() as connection:
        origin = connection.execute(text("SELECT origin FROM leads")).scalar()
    engine.dispose()
    assert origin == "unknown"
    command.downgrade(config, "base")


def test_migrations_upgrade_downgrade_and_reupgrade() -> None:
    ensure_database("atlas_migration_test")
    engine = create_engine(MIGRATION_DATABASE_URL, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()

    config = _config()
    command.upgrade(config, "head")

    engine = create_engine(MIGRATION_DATABASE_URL, pool_pre_ping=True)
    tables = set(inspect(engine).get_table_names())
    assert {
        "users",
        "organizations",
        "memberships",
        "sessions",
        "companies",
        "documents",
        "conversations",
        "agent_runs",
        "agent_events",
        "approvals",
        "webhook_keys",
        "execution_intents",
        "workflow_runs",
        "email_messages",
        "calendar_bookings",
        "model_versions",
        "lead_predictions",
        "operation_traces",
        "evaluation_runs",
    } <= tables
    with engine.connect() as connection:
        vector_installed = connection.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
    assert vector_installed == 1
    engine.dispose()

    command.downgrade(config, "base")
    engine = create_engine(MIGRATION_DATABASE_URL, pool_pre_ping=True)
    assert "users" not in inspect(engine).get_table_names()
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(MIGRATION_DATABASE_URL, pool_pre_ping=True)
    assert "sessions" in inspect(engine).get_table_names()
    engine.dispose()
