"""Same-origin HTTPS smoke test for the staging Compose stack.

The script talks only to the atlas-staging project. It seeds that project's
database while the API is in development, then restarts the API in production.
It does not read or write the local development database.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
from http.client import HTTPSConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "infrastructure" / "compose.staging.yaml"
ENV_FILE = ROOT / "infrastructure" / "staging" / ".env"
CA_FILE = ROOT / "infrastructure" / "staging" / "local-ca.crt"
PROJECT = "atlas-staging"
PRIVATE_PORTS = {
    "postgres": 5432,
    "api": 8000,
    "mailpit": 8025,
    "n8n": 5678,
    "ollama": 11434,
}


class SmokeFailure(RuntimeError):
    pass


class PinnedHTTPSConnection(HTTPSConnection):
    """Dial 127.0.0.1 and present the staging hostname for SNI and Host."""

    def connect(self) -> None:
        raw = socket.create_connection(("127.0.0.1", self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


class StagingClient:
    def __init__(self, origin: str) -> None:
        host_port = origin.removeprefix("https://")
        if host_port.count(":") == 1:
            host, port_text = host_port.split(":")
            port = int(port_text)
        else:
            host = host_port
            port = 443
        self.origin = origin.rstrip("/")
        self.host = host
        self.port = port
        self.context = ssl.create_default_context()
        self.cookies: dict[str, str] = {}

    def trust(self, ca_file: Path) -> None:
        self.context.load_verify_locations(cafile=str(ca_file))

    def clear(self) -> None:
        self.cookies.clear()

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        csrf: str | None = None,
        accept: str = "application/json",
    ) -> tuple[int, dict[str, object], str, list[str]]:
        payload = None if body is None else json.dumps(body).encode()
        headers = {"Accept": accept}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in self.cookies.items())
        if csrf:
            headers["X-CSRF-Token"] = csrf
        connection = PinnedHTTPSConnection(self.host, self.port, context=self.context, timeout=30)
        try:
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            set_cookies = response.headers.get_all("Set-Cookie") or []
            for header in set_cookies:
                _store_cookie(self.cookies, header)
            text = raw.decode(errors="replace")
            if not text:
                return response.status, {}, text, set_cookies
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = {"text": text[:800]}
            if not isinstance(parsed, dict):
                parsed = {"value": parsed}
            return response.status, parsed, text, set_cookies
        except (OSError, ssl.SSLError, urllib.error.URLError) as exc:
            raise SmokeFailure(f"{method} {path} failed: {exc}") from exc
        finally:
            connection.close()


def compose(
    *args: str, check: bool = True, stream: bool = False
) -> subprocess.CompletedProcess[str]:
    command = [
        "docker",
        "compose",
        "--project-name",
        PROJECT,
        "--project-directory",
        str(ROOT / "infrastructure"),
        "--env-file",
        str(ENV_FILE),
        "-f",
        str(COMPOSE_FILE),
        *args,
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=not stream,
        check=False,
    )
    if check and result.returncode != 0:
        raise SmokeFailure(f"{' '.join(args)} failed\n{result.stdout}\n{result.stderr}".strip())
    return result


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = value
    return values


def write_env(values: dict[str, str]) -> None:
    ENV_FILE.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")


def ensure_env() -> dict[str, str]:
    if ENV_FILE.exists():
        return read_env()
    values = {
        "STAGING_ENVIRONMENT": "development",
        "STAGING_SECRET_KEY": secrets.token_hex(32),
        "STAGING_POSTGRES_USER": "atlas",
        "STAGING_POSTGRES_PASSWORD": secrets.token_hex(24),
        "STAGING_POSTGRES_DB": "atlas",
        "STAGING_N8N_ENCRYPTION_KEY": secrets.token_hex(32),
        "STAGING_HOST": "atlas.localhost",
        "STAGING_HTTP_PORT": "8080",
        "STAGING_HTTPS_PORT": "8443",
        "STAGING_CORS_ORIGINS": "https://atlas.localhost:8443",
        "SEED_ADMIN_EMAIL": "admin@example.com",
        "SEED_ADMIN_PASSWORD": secrets.token_hex(24),
        "SEED_ADMIN_NAME": "Staging Admin",
        "SEED_STAFF_EMAIL": "staff@example.com",
        "SEED_STAFF_PASSWORD": secrets.token_hex(24),
        "SEED_STAFF_NAME": "Staging Staff",
        "SEED_OUTSIDER_EMAIL": "outsider@example.org",
        "SEED_OUTSIDER_PASSWORD": secrets.token_hex(24),
        "SEED_OUTSIDER_NAME": "Staging Outsider",
        "STAGING_LLM_PROVIDER": "openai",
        "STAGING_LLM_BASE_URL": "https://api.openai.com/v1",
        "STAGING_LLM_API_KEY": "",
        "STAGING_LLM_MODEL": "gpt-4o-mini",
        "STAGING_HOOK_KEY_ID": "",
        "STAGING_HOOK_SECRET": "",
        "STAGING_SMTP_FROM": "atlas@localhost",
        "STAGING_LOG_LEVEL": "INFO",
    }
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_env(values)
    print("Wrote infrastructure/staging/.env with generated secrets")
    return values


def base_url(values: dict[str, str]) -> str:
    host = values.get("STAGING_HOST", "atlas.localhost")
    port = values.get("STAGING_HTTPS_PORT", "443")
    if port == "443":
        return f"https://{host}"
    return f"https://{host}:{port}"


def wait_healthy(timeout: float = 300) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = compose("ps", "--format", "{{.Service}} {{.Health}} {{.Status}}", check=False)
        rows = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        by_service = {line.split()[0]: line for line in rows if line.split()}
        api_ok = "healthy" in by_service.get("api", "")
        web_ok = "healthy" in by_service.get("web", "")
        caddy_ok = "caddy" in by_service
        if api_ok and web_ok and caddy_ok:
            return
        time.sleep(3)
    raise SmokeFailure("api, web, or caddy did not become ready")


def assert_private_ports() -> None:
    result = compose("ps", "--format", "{{.Service}}\t{{.Ports}}")
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        service, _, ports = line.partition("\t")
        if service == "caddy":
            if "->" not in ports:
                raise SmokeFailure("Caddy is not publishing the HTTPS entry")
            continue
        if "->" in ports:
            raise SmokeFailure(f"{service} publishes a port: {ports}")
    for service, port in PRIVATE_PORTS.items():
        mapped = compose("port", service, str(port), check=False)
        published = mapped.stdout.strip()
        # Compose prints "invalid IP:0" when the container port is not published.
        if mapped.returncode == 0 and published and "invalid ip" not in published.lower():
            raise SmokeFailure(f"{service} port {port} is published at {published}")


def assert_staging_database() -> None:
    probe = (
        "import os, sys; url = os.environ.get('ATLAS_DATABASE_URL', ''); "
        "ok = url.startswith('postgresql') and '@postgres:5432/' in url; sys.exit(0 if ok else 1)"
    )
    result = compose("exec", "-T", "api", "python", "-c", probe, check=False)
    if result.returncode != 0:
        raise SmokeFailure("refusing to seed because the API is not pointed at the staging database")


def assert_server_user_and_volumes() -> None:
    uid = compose(
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "print(open('/proc/1/status').read().split('Uid:')[1].split()[0])",
    )
    if uid.stdout.strip() != "10001":
        raise SmokeFailure(f"API process uid is {uid.stdout.strip()}, expected 10001")
    write = (
        "from pathlib import Path\n"
        "for folder in ('/var/lib/atlas/storage', '/var/lib/atlas/models'):\n"
        "    path = Path(folder) / '.write-probe'\n"
        "    path.write_text('ok')\n"
        "    path.unlink()\n"
    )
    result = compose("exec", "-T", "-u", "atlas", "api", "python", "-c", write, check=False)
    if result.returncode != 0:
        raise SmokeFailure(f"atlas cannot write the data volumes\n{result.stderr}")


def copy_ca() -> None:
    deadline = time.monotonic() + 60
    last = ""
    while time.monotonic() < deadline:
        result = compose(
            "cp",
            "caddy:/data/caddy/pki/authorities/local/root.crt",
            str(CA_FILE),
            check=False,
        )
        if result.returncode == 0 and CA_FILE.is_file():
            return
        last = result.stderr.strip()
        time.sleep(2)
    raise SmokeFailure(f"Caddy local CA was not available: {last}")


def install_ca_for_browser() -> None:
    if os.name != "nt":
        return
    # Windows asks before a new root is trusted. Accept that dialog for the
    # Caddy CA copied from this stack. Direct registry writes are reverted.
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def window_text(hwnd: int) -> str:
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value

    def confirm_root_dialog() -> None:
        def visit(hwnd: wintypes.HWND, _lparam: wintypes.LPARAM) -> bool:
            if not user32.IsWindowVisible(hwnd) or window_text(hwnd) != "Security Warning":
                return True

            def click(child: wintypes.HWND, _child_param: wintypes.LPARAM) -> bool:
                if window_text(child).replace("&", "").lower() == "yes":
                    user32.SendMessageW(child, 0x00F5, 0, 0)
                return True

            user32.EnumChildWindows(hwnd, enum_proc(click), 0)
            return True

        user32.EnumWindows(enum_proc(visit), 0)

    proc = subprocess.Popen(
        ["certutil", "-user", "-addstore", "Root", str(CA_FILE)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and proc.poll() is None:
        confirm_root_dialog()
        time.sleep(0.2)
    try:
        stdout, _stderr = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise SmokeFailure("Trusting the Caddy CA timed out") from None
    if proc.returncode != 0:
        raise SmokeFailure(f"Could not trust the Caddy CA\n{stdout}")


def run_browser(origin: str, values: dict[str, str]) -> None:
    env = os.environ.copy()
    env.update(
        {
            "STAGING_BASE_URL": origin,
            "SEED_ADMIN_EMAIL": values["SEED_ADMIN_EMAIL"],
            "SEED_ADMIN_PASSWORD": values["SEED_ADMIN_PASSWORD"],
            "SEED_ADMIN_NAME": values["SEED_ADMIN_NAME"],
        }
    )
    channels = [env.get("STAGING_BROWSER_CHANNEL", ""), "msedge", "chrome"]
    seen: list[str] = []
    last = ""
    for channel in channels:
        if not channel or channel in seen:
            continue
        seen.append(channel)
        env["STAGING_BROWSER_CHANNEL"] = channel
        try:
            result = subprocess.run(
                ["node", "scripts/staging-browser.mjs"],
                cwd=ROOT / "apps" / "web",
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            last = f"{channel} timed out\n{exc.stdout}\n{exc.stderr}"
            continue
        if result.returncode == 0:
            print(result.stdout.strip())
            return
        last = f"{channel}\n{result.stdout}\n{result.stderr}"
    raise SmokeFailure(f"browser login failed\n{last}")


def _store_cookie(cookies: dict[str, str], header: str) -> None:
    parts = [part.strip() for part in header.split(";")]
    if not parts or "=" not in parts[0]:
        return
    name, value = parts[0].split("=", 1)
    lowered = header.lower()
    if value == "" or "max-age=0" in lowered:
        cookies.pop(name, None)
        return
    cookies[name] = value


def _login(client: StagingClient, email: str, password: str) -> tuple[int, dict[str, object], list[str]]:
    status, payload, _text, set_cookies = client.request(
        "POST",
        "/api/v1/auth/login",
        {"email": email, "password": password},
    )
    return status, payload, set_cookies


def _error_code(payload: dict[str, object]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if isinstance(code, str):
            return code
    return ""


def _membership(payload: dict[str, object], slug: str) -> str:
    memberships = payload.get("memberships")
    if not isinstance(memberships, list):
        raise SmokeFailure("login response has no memberships")
    for item in memberships:
        if isinstance(item, dict) and item.get("organization_slug") == slug:
            organization_id = item.get("organization_id")
            if isinstance(organization_id, str):
                return organization_id
    raise SmokeFailure(f"no membership for {slug}")


def _csrf(payload: dict[str, object]) -> str:
    token = payload.get("csrf_token")
    if not isinstance(token, str) or not token:
        raise SmokeFailure("login response has no csrf token")
    return token


def assert_cookie(set_cookies: list[str]) -> None:
    session = next((item for item in set_cookies if item.startswith("atlas_session=")), "")
    if not session:
        raise SmokeFailure("login did not set atlas_session")
    lowered = session.lower()
    for flag in ("httponly", "secure", "samesite=lax"):
        if flag not in lowered:
            raise SmokeFailure(f"session cookie is missing {flag}: {session}")
    if "domain=" in lowered:
        raise SmokeFailure("session cookie sets Domain and would leave the host")


def exercise_https(client: StagingClient, values: dict[str, str]) -> None:
    status, _payload, text, _cookies = client.request("GET", "/login", accept="text/html")
    if status != 200 or "Sign in" not in text:
        raise SmokeFailure(f"Caddy did not serve Next.js login, status {status}")
    status, payload, _text, _cookies = client.request("GET", "/api/v1/health")
    if status != 200 or payload.get("service") != "atlas-api":
        raise SmokeFailure(f"/api was not forwarded intact: {status} {payload}")
    status, payload, _text, _cookies = client.request("GET", "/docs")
    if status != 404:
        raise SmokeFailure(f"production still exposes /docs: {status}")

    client.clear()
    status, payload, set_cookies = _login(client, values["SEED_ADMIN_EMAIL"], values["SEED_ADMIN_PASSWORD"])
    if status != 200:
        raise SmokeFailure(f"admin login failed: {status} {payload}")
    assert_cookie(set_cookies)
    admin_csrf = _csrf(payload)
    atlas_id = _membership(payload, "atlas-demo")
    status, me, _text, _cookies = client.request("GET", "/api/v1/auth/me")
    if status != 200 or me.get("csrf_token") != admin_csrf:
        raise SmokeFailure("session did not persist on /auth/me")

    status, denied, _text, _cookies = client.request(
        "POST",
        f"/api/v1/organizations/{atlas_id}/companies",
        {"name": "Staging HTTPS probe"},
    )
    if status != 403 or _error_code(denied) != "csrf_failed":
        raise SmokeFailure(f"missing CSRF was accepted: {status} {denied}")
    status, created, _text, _cookies = client.request(
        "POST",
        f"/api/v1/organizations/{atlas_id}/companies",
        {"name": "Staging HTTPS probe"},
        csrf=admin_csrf,
    )
    if status != 201 or created.get("name") != "Staging HTTPS probe":
        raise SmokeFailure(f"CSRF create failed: {status} {created}")
    company_id = created.get("id")
    if not isinstance(company_id, str):
        raise SmokeFailure("create response has no company id")

    client.clear()
    status, staff_payload, _cookies = _login(
        client, values["SEED_STAFF_EMAIL"], values["SEED_STAFF_PASSWORD"]
    )
    if status != 200:
        raise SmokeFailure(f"staff login failed: {status}")
    staff_csrf = _csrf(staff_payload)
    status, page, _text, _cookies = client.request("GET", f"/api/v1/organizations/{atlas_id}/companies")
    names = [item.get("name") for item in page.get("items", [])] if isinstance(page.get("items"), list) else []
    if status != 200 or "Staging HTTPS probe" not in names:
        raise SmokeFailure(f"staff cannot see the company created over HTTPS: {status} {page}")
    status, forbidden, _text, _cookies = client.request(
        "POST",
        f"/api/v1/organizations/{atlas_id}/approvals/00000000-0000-0000-0000-000000000000/approve",
        csrf=staff_csrf,
    )
    if status != 403 or _error_code(forbidden) != "forbidden":
        raise SmokeFailure(f"staff approval was not forbidden: {status} {forbidden}")

    client.clear()
    status, outsider_payload, _cookies = _login(
        client, values["SEED_OUTSIDER_EMAIL"], values["SEED_OUTSIDER_PASSWORD"]
    )
    if status != 200:
        raise SmokeFailure(f"outsider login failed: {status}")
    status, hidden, _text, _cookies = client.request("GET", f"/api/v1/organizations/{atlas_id}/companies")
    if status != 404 or _error_code(hidden) != "not_found":
        raise SmokeFailure(f"outsider can see another organization: {status} {hidden}")
    northwind_id = _membership(outsider_payload, "northwind")
    status, own, _text, _cookies = client.request("GET", f"/api/v1/organizations/{northwind_id}/companies")
    if status != 200:
        raise SmokeFailure(f"outsider cannot read their own organization: {status} {own}")

    client.clear()
    status, admin_again, set_cookies = _login(
        client, values["SEED_ADMIN_EMAIL"], values["SEED_ADMIN_PASSWORD"]
    )
    if status != 200:
        raise SmokeFailure("admin login failed before logout")
    admin_csrf = _csrf(admin_again)
    status, deleted, _text, _cookies = client.request(
        "DELETE",
        f"/api/v1/organizations/{atlas_id}/companies/{company_id}",
        csrf=admin_csrf,
    )
    if status != 204:
        raise SmokeFailure(f"cleanup delete failed: {status} {deleted}")
    saved = dict(client.cookies)
    status, rejected, _text, _cookies = client.request("POST", "/api/v1/auth/logout")
    if status != 403 or _error_code(rejected) != "csrf_failed":
        raise SmokeFailure(f"logout without CSRF was accepted: {status} {rejected}")
    status, _empty, _text, cleared = client.request("POST", "/api/v1/auth/logout", csrf=admin_csrf)
    if status != 204:
        raise SmokeFailure(f"logout failed: {status}")
    if not any(item.startswith("atlas_session=") and "max-age=0" in item.lower() for item in cleared):
        raise SmokeFailure("logout did not clear the session cookie")
    client.cookies = saved
    status, afterwards, _text, _cookies = client.request("GET", "/api/v1/auth/me")
    if status != 401 or _error_code(afterwards) != "unauthenticated":
        raise SmokeFailure(f"revoked session was still accepted: {status} {afterwards}")


def _login_status(client: StagingClient, values: dict[str, str]) -> int:
    status, _payload, _text, _cookies = client.request(
        "POST",
        "/api/v1/auth/login",
        {"email": values["SEED_ADMIN_EMAIL"], "password": values["SEED_ADMIN_PASSWORD"]},
    )
    client.clear()
    return status


def main() -> int:
    skip_browser = "--skip-browser" in sys.argv or os.environ.get("ATLAS_STAGING_SKIP_BROWSER") == "1"
    values = ensure_env()
    print("Building and starting the staging stack")
    compose("up", "-d", "--build", stream=True)
    wait_healthy()
    assert_private_ports()
    copy_ca()
    client = StagingClient(base_url(values))
    client.trust(CA_FILE)
    _wait_ready(client)
    if values.get("STAGING_ENVIRONMENT") != "production" or _login_status(client, values) != 200:
        if values.get("STAGING_ENVIRONMENT") != "development" and _login_status(client, values) != 200:
            raise SmokeFailure(
                "Staging is in production and the seed login failed. Production refuses the seed."
            )
        if _login_status(client, values) != 200:
            assert_staging_database()
            seeded = compose(
                "exec", "-T", "-u", "atlas", "api", "python", "-m", "app.scripts.seed", check=False
            )
            if seeded.returncode != 0:
                raise SmokeFailure(f"seed failed\n{seeded.stdout}\n{seeded.stderr}")
        if values.get("STAGING_ENVIRONMENT") != "production":
            values["STAGING_ENVIRONMENT"] = "production"
            write_env(values)
            compose("up", "-d", "--no-deps", "--force-recreate", "api")
            compose("up", "-d", "--no-deps", "--force-recreate", "caddy")
            wait_healthy()
            _wait_ready(client)
    assert_server_user_and_volumes()
    exercise_https(client, values)
    print("https_ok", base_url(values))
    if not skip_browser:
        install_ca_for_browser()
        run_browser(base_url(values), values)
    return 0


def _wait_ready(client: StagingClient) -> None:
    deadline = time.monotonic() + 120
    last = "no response"
    while time.monotonic() < deadline:
        try:
            status, payload, _text, _cookies = client.request("GET", "/api/v1/ready")
        except SmokeFailure as exc:
            last = str(exc)
            time.sleep(2)
            continue
        if status == 200 and payload.get("database") == "ok":
            return
        last = str(payload)
        time.sleep(2)
    raise SmokeFailure(f"ready check failed: {last}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
