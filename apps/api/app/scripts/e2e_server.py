"""API for the browser test. Uses atlas_e2e and deterministic providers."""

from __future__ import annotations

import os
import uuid


def install_provider_transport() -> None:
    """Install deterministic provider I/O only for this disposable server."""
    if os.environ.get("ATLAS_E2E_PROVIDER_TRANSPORT") != "1":
        return
    import httpx
    from sqlalchemy.orm import Session

    from app.api.v1 import integrations as integrations_api
    from app.integrations.language import OpenAICompatibleChatClient
    from app.integrations.resolver import resolve_settings

    def handler(request: httpx.Request) -> httpx.Response:
        authorization = request.headers.get("authorization", "")
        if "timeout" in authorization:
            raise httpx.ReadTimeout("e2e timeout", request=request)
        if "invalid" in authorization:
            return httpx.Response(401, request=request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n',
            request=request,
        )

    def e2e_chat_client(
        db: Session | None = None, organization_id: uuid.UUID | None = None
    ) -> OpenAICompatibleChatClient:
        assert db is not None and organization_id is not None
        settings = resolve_settings(db, organization_id, "chat")
        return OpenAICompatibleChatClient(settings, transport=httpx.MockTransport(handler))

    integrations_api.get_chat_client = e2e_chat_client


def main() -> None:
    from tests.bootstrap import postgres_url

    os.environ["ATLAS_DATABASE_URL"] = postgres_url("atlas_e2e")
    os.environ["ATLAS_ENVIRONMENT"] = "development"
    os.environ["ATLAS_LLM_PROVIDER"] = "double"
    os.environ["ATLAS_LLM_API_KEY"] = ""
    os.environ["ATLAS_LLM_MODEL"] = "gpt-4o-mini"
    os.environ["ATLAS_EMBEDDING_PROVIDER"] = "double"
    os.environ["ATLAS_EMBEDDING_API_KEY"] = ""
    os.environ["ATLAS_EMBEDDING_MODEL"] = "text-embedding-3-small"
    os.environ["ATLAS_EMBEDDING_DIMENSIONS"] = "1536"
    os.environ["ATLAS_PUBLIC_DEMO"] = "false"
    os.environ["ATLAS_N8N_LEAD_WEBHOOK_URL"] = ""
    web_port = os.environ.get("ATLAS_E2E_WEB_PORT", "3010")
    os.environ["ATLAS_CORS_ORIGINS"] = f"http://127.0.0.1:{web_port},http://localhost:{web_port}"
    os.environ["ATLAS_EMAIL_MODE"] = "sandbox"
    os.environ["ATLAS_SMTP_HOST"] = "127.0.0.1"
    os.environ["ATLAS_LOG_LEVEL"] = "INFO"

    from app.core.config import get_settings

    get_settings.cache_clear()
    install_provider_transport()
    import uvicorn
    from app.main import create_app

    uvicorn.run(
        create_app(),
        host="127.0.0.1",
        port=int(os.environ.get("ATLAS_E2E_API_PORT", "8010")),
    )


if __name__ == "__main__":
    main()
