"""API for the browser test. Uses atlas_e2e and deterministic providers."""

from __future__ import annotations

import os


def main() -> None:
    from tests.bootstrap import postgres_url

    os.environ["ATLAS_DATABASE_URL"] = postgres_url("atlas_e2e")
    os.environ["ATLAS_ENVIRONMENT"] = "development"
    os.environ["ATLAS_LLM_PROVIDER"] = "double"
    os.environ["ATLAS_EMBEDDING_PROVIDER"] = "double"
    os.environ["ATLAS_N8N_LEAD_WEBHOOK_URL"] = ""
    os.environ["ATLAS_CORS_ORIGINS"] = "http://127.0.0.1:3010,http://localhost:3010"
    os.environ["ATLAS_EMAIL_MODE"] = "sandbox"
    os.environ["ATLAS_SMTP_HOST"] = "127.0.0.1"

    from app.core.config import get_settings

    get_settings.cache_clear()
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8010)


if __name__ == "__main__":
    main()
