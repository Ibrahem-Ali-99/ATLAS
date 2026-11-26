"""Release smoke test for the public origin. It does not sign in or write a row."""

from __future__ import annotations

import argparse
import http.client
import json
import socket
import ssl
from urllib.parse import urlsplit

HIDDEN = ("/docs", "/openapi.json", "/redoc")


class _NamedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        connect_host: str,
        port: int,
        *,
        context: ssl.SSLContext,
        timeout: int,
        server_hostname: str,
    ) -> None:
        super().__init__(connect_host, port, context=context, timeout=timeout)
        self._server_hostname = server_hostname

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self._server_hostname)


def _connect_host(host: str, port: int) -> str:
    try:
        socket.getaddrinfo(host, port)
    except socket.gaierror:
        if host == "localhost" or host.endswith(".localhost"):
            return "127.0.0.1"
        raise
    return host


def _open(
    url: str,
    cafile: str | None,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
):
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    request_headers = dict(headers or {})
    request_headers.setdefault("Host", host if port in {80, 443} else f"{host}:{port}")
    connect_host = _connect_host(host, port)
    if parsed.scheme == "https":
        context = ssl.create_default_context(cafile=cafile) if cafile else ssl._create_unverified_context()
        connection: http.client.HTTPConnection = _NamedHTTPSConnection(
            connect_host, port, context=context, timeout=20, server_hostname=host
        )
    else:
        connection = http.client.HTTPConnection(connect_host, port, timeout=20)
    try:
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        payload = response.read()
        collected: dict[str, str] = {}
        for key, value in response.getheaders():
            previous = collected.get(key)
            collected[key] = value if previous is None else f"{previous}, {value}"
        return response.status, collected, payload
    finally:
        connection.close()


def problems(base_url: str, cafile: str | None = None, http_url: str | None = None) -> list[str]:
    issues: list[str] = []
    origin = base_url.rstrip("/")
    status, headers, home = _open(origin + "/", cafile)
    if status != 200 or b"<!DOCTYPE html>" not in home or b"Case study" not in home or b"Sign in" not in home:
        issues.append("the public home page is not served by the web app")
    for path in ("/demo", "/case-study", "/login"):
        page_status, _, _ = _open(origin + path, cafile)
        if page_status != 200:
            issues.append(f"{path} returned {page_status}")
    demo_status, _, demo = _open(origin + "/demo", cafile)
    if demo_status == 200 and b"Harbor" not in demo:
        issues.append("the demo page does not describe the fictional workspace")
    image_status, image_headers, _ = _open(origin + "/portfolio/01-overview.png", cafile)
    image_type = ""
    for key, value in image_headers.items():
        if key.lower() == "content-type":
            image_type = value
    if image_status != 200 or not image_type.startswith("image/"):
        issues.append("the public capture was not served")
    health_status, _, health = _open(origin + "/api/v1/health", cafile)
    if health_status != 200 or b'"service":"atlas-api"' not in health.replace(b" ", b""):
        issues.append("the API health route is not forwarded intact")
    ready_status, _, ready = _open(origin + "/api/v1/ready", cafile)
    if ready_status != 200 or b'"database":"ok"' not in ready.replace(b" ", b""):
        issues.append("the API is not ready")
    me_status, me_headers, _ = _open(origin + "/api/v1/auth/me", cafile)
    if me_status != 401 or "atlas_session=" in _cookies(me_headers):
        issues.append("an anonymous visitor received a workspace session")
    login_status, login_headers, _ = _open(
        origin + "/api/v1/auth/login",
        cafile,
        method="POST",
        body=b'{"email":"nobody@example.com","password":"not-a-real-password"}',
        headers={"Content-Type": "application/json"},
    )
    if login_status != 401 or "atlas_session=" in _cookies(login_headers):
        issues.append("a failed login was treated as a session")
    for path in HIDDEN:
        hidden_status, _, _ = _open(origin + path, cafile)
        if hidden_status != 404:
            issues.append(f"{path} is visible on the public origin")
    def header(name: str) -> str:
        for key, value in headers.items():
            if key.lower() == name:
                return value
        return ""

    if header("x-content-type-options") != "nosniff":
        issues.append("X-Content-Type-Options is missing")
    if header("x-frame-options") != "DENY":
        issues.append("X-Frame-Options is missing")
    if header("server").strip():
        issues.append("the Server header is present")
    if "localhost" in origin or "127.0.0.1" in origin:
        if header("strict-transport-security").strip():
            issues.append("HSTS is set on a local proof name")
    redirect_target = http_url.rstrip("/") if http_url else _plain_http(origin)
    redirect_status, redirect_headers, _ = _open(redirect_target + "/", None)
    location = ""
    for key, value in redirect_headers.items():
        if key.lower() == "location":
            location = value
    if redirect_status != 308 or not location.startswith("https://"):
        issues.append("HTTP does not redirect to HTTPS")
    return issues


def _cookies(headers: dict[str, str]) -> str:
    return " ".join(value for key, value in headers.items() if key.lower() == "set-cookie")


def _plain_http(origin: str) -> str:
    host = origin.split("://", 1)[1]
    if host.endswith(":443"):
        host = host[:-4]
    elif ":" in host:
        raise ValueError("Pass the HTTP URL when HTTPS is not on port 443")
    return f"http://{host}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--http-url", default="")
    parser.add_argument("--ca", default="")
    args = parser.parse_args()
    issues = problems(args.base_url, args.ca or None, args.http_url or None)
    print(json.dumps({"ok": not issues, "problems": issues}))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
