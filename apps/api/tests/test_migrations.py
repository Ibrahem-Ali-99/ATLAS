import os

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from tests.bootstrap import API_ROOT, MIGRATION_DATABASE_URL, ensure_database


def _config() -> Config:
    os.environ["ALEMBIC_DATABASE_URL"] = MIGRATION_DATABASE_URL
    return Config(str(API_ROOT / "alembic.ini"))


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
