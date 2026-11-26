import re
import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.get_logger(__name__)
_WIDGET_SESSION = re.compile(r"^(/api/v1/widget/[^/]+/sessions/)[^/]+")
_CAMPAIGN_PREFERENCE = re.compile(r"^(/api/v1/campaign-preferences/)[^/]+")


class AtlasCorsMiddleware:
    def __init__(self, app: ASGIApp, workspace_origins: list[str]) -> None:
        self.workspace = CORSMiddleware(
            app,
            allow_origins=workspace_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token"],
            expose_headers=["X-Request-ID"],
        )
        self.widget = CORSMiddleware(
            app,
            allow_origins=["*"],
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith("/api/v1/widget/"):
            # These routes use the widget's origin list and a visitor token.
            await self.widget(scope, receive, send)
            return
        await self.workspace(scope, receive, send)


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = MutableHeaders(raw=message["headers"])
                headers.append("x-request-id", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            path = _WIDGET_SESSION.sub(r"\1{session_token}", str(scope.get("path", "")))
            path = _CAMPAIGN_PREFERENCE.sub(r"\1{preference_token}", path)
            fields = {
                "method": scope.get("method"),
                "path": path,
                "status": status_code,
                "duration_ms": duration_ms,
            }
            if path.endswith(("/health", "/ready")):
                logger.debug("request", **fields)
            else:
                logger.info("request", **fields)
            structlog.contextvars.clear_contextvars()
