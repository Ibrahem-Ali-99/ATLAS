"""Score the fresh Plover set with the real chat provider.

Run with ATLAS_FINAL_EVAL=yes and ATLAS_LIVE_RAG=yes.
Inserts rows only in a transaction on atlas_test and rolls them back.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tests.test_final_retrieval import run_final


def main() -> None:
    final = os.environ.get("ATLAS_FINAL_EVAL") == "yes"
    live = os.environ.get("ATLAS_LIVE_RAG") == "yes"
    ready = final and live
    if not ready:
        raise SystemExit("final generation is blocked")
    engine = create_engine(_test_database_url())
    with Session(engine) as db:
        try:
            run_final(db)
        finally:
            db.rollback()


def _test_database_url() -> str:
    values = _postgres_values()
    user = quote_plus(values.get("POSTGRES_USER", "atlas"))
    password = quote_plus(values.get("POSTGRES_PASSWORD", "atlas"))
    host = values.get("POSTGRES_HOST", "127.0.0.1")
    port = values.get("POSTGRES_PORT", "5432")
    name = os.environ.get("ATLAS_TEST_DATABASE", "atlas_test")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


def _postgres_values() -> dict[str, str]:
    root = Path(__file__).resolve().parents[4]
    env_file = root / ".env"
    found: dict[str, str] = {}
    if not env_file.is_file():
        return found
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip().startswith("POSTGRES_"):
            found[key.strip()] = value.strip().strip('"').strip("'")
    return found


if __name__ == "__main__":
    main()
