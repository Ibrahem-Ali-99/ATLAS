"""API for the browser test. Uses a per-run database and deterministic providers."""

from __future__ import annotations

import os
import uuid
from email import policy
from email.parser import BytesParser
from typing import Annotated, Literal

from fastapi import Path


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
        db: Session | None = None,
        organization_id: uuid.UUID | None = None,
        *,
        for_verification: bool = False,
    ) -> OpenAICompatibleChatClient:
        assert db is not None and organization_id is not None
        settings = resolve_settings(db, organization_id, "chat", for_verification=for_verification)
        return OpenAICompatibleChatClient(settings, transport=httpx.MockTransport(handler))

    integrations_api.get_chat_client = e2e_chat_client


def install_resend_transport() -> None:
    if os.environ.get("ATLAS_E2E_RESEND_TRANSPORT") != "1":
        return
    from app.domains.integrations import domain_service
    from app.integrations.domain_verification import DnsRecord, DomainStatus

    class FakeResend:
        def __init__(self) -> None:
            self.verified = set[str]()

        def register(self, domain: str) -> DomainStatus:
            return DomainStatus(
                provider_domain_id=f"e2e-{domain}",
                verified=False,
                records=[DnsRecord("TXT", f"_resend.{domain}", "resend-verification=e2e")],
                evidence={"provider": "resend", "status": "pending"},
            )

        def status(self, provider_domain_id: str) -> DomainStatus:
            verified = provider_domain_id in self.verified
            return DomainStatus(
                provider_domain_id=provider_domain_id,
                verified=verified,
                records=[DnsRecord("TXT", "_resend.example.test", "resend-verification=e2e")],
                evidence={"provider": "resend", "status": "verified" if verified else "pending"},
            )

        def start_verification(self, provider_domain_id: str) -> None:
            self.verified.add(provider_domain_id)

        def revoke(self, provider_domain_id: str) -> None:
            return None

    transport = FakeResend()
    domain_service.ResendDomainProvider = lambda _token: transport  # type: ignore[assignment,misc]


def main() -> None:
    smtp_port = os.environ.get("ATLAS_SMTP_PORT")
    from app.scripts.e2e_database import database_name
    from tests.bootstrap import postgres_url
    from tests.smtp_sink import start_process_sink

    os.environ["ATLAS_DATABASE_URL"] = postgres_url(database_name())
    os.environ["ATLAS_ENVIRONMENT"] = "development"
    os.environ["ATLAS_LLM_PROVIDER"] = "double"
    os.environ["ATLAS_LLM_API_KEY"] = ""
    os.environ["ATLAS_LLM_MODEL"] = "gpt-4o-mini"
    os.environ["ATLAS_EMBEDDING_PROVIDER"] = "double"
    os.environ["ATLAS_EMBEDDING_API_KEY"] = ""
    os.environ["ATLAS_EMBEDDING_MODEL"] = "text-embedding-3-small"
    os.environ["ATLAS_EMBEDDING_DIMENSIONS"] = "1536"
    os.environ["ATLAS_PUBLIC_DEMO"] = "false"
    os.environ["ATLAS_PUBLIC_INFERENCE_ENABLED"] = "false"
    os.environ["ATLAS_PUBLIC_LLM_AUTHORIZED"] = "false"
    os.environ["ATLAS_PUBLIC_LLM_API_KEY"] = ""
    os.environ["ATLAS_PUBLIC_EMBEDDING_AUTHORIZED"] = "false"
    os.environ["ATLAS_PUBLIC_EMBEDDING_API_KEY"] = ""
    os.environ["ATLAS_N8N_LEAD_WEBHOOK_URL"] = ""
    web_port = os.environ.get("ATLAS_E2E_WEB_PORT", "3010")
    os.environ["ATLAS_CORS_ORIGINS"] = f"http://127.0.0.1:{web_port},http://localhost:{web_port}"
    os.environ["ATLAS_EMAIL_MODE"] = "sandbox"
    os.environ["ATLAS_CAMPAIGN_PUBLIC_URL"] = (
        f"http://127.0.0.1:{os.environ.get('ATLAS_E2E_API_PORT', '8010')}"
    )
    os.environ["ATLAS_SMTP_HOST"] = "127.0.0.1"
    if os.environ.get("ATLAS_E2E_SKIP_MAILPIT") == "1":
        smtp_port = str(start_process_sink().port)
    if smtp_port is not None:
        os.environ["ATLAS_SMTP_PORT"] = smtp_port
    os.environ["ATLAS_LOG_LEVEL"] = "INFO"

    from app.core.config import get_settings

    get_settings.cache_clear()
    install_provider_transport()
    install_resend_transport()
    import uvicorn

    from app.core.database import SessionLocal
    from app.main import create_app
    from app.scripts.prepare_populated_e2e import sample_workspace

    app = create_app()

    @app.post("/_acceptance/sample-workspace/{slug}", include_in_schema=False)
    def prepare_sample_workspace(
        slug: Annotated[str, Path(pattern=r"^sample-e2e-\d+-\d+$")],
        operation: Literal["prepare", "verify", "cleanup"],
    ) -> dict[str, object]:
        with SessionLocal() as db:
            return sample_workspace(
                db, slug, verify=operation == "verify", cleanup=operation == "cleanup"
            )

    if os.environ.get("ATLAS_E2E_SKIP_MAILPIT") == "1":
        sink = start_process_sink()

        @app.get("/_acceptance/mail", include_in_schema=False)
        def list_accepted_test_mail(recipient: str) -> list[dict[str, str]]:
            with sink.lock:
                accepted = tuple(sink.messages)
            replies = []
            for raw in accepted:
                message = BytesParser(policy=policy.default).parsebytes(raw)
                if str(message.get("To", "")).casefold() != recipient.casefold():
                    continue
                content = message.get_body(preferencelist=("plain",))
                replies.append(
                    {
                        "subject": str(message.get("Subject", "")),
                        "body": content.get_content() if content else "",
                    }
                )
            return replies

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ.get("ATLAS_E2E_API_PORT", "8010")),
        access_log=False,
    )


if __name__ == "__main__":
    main()
