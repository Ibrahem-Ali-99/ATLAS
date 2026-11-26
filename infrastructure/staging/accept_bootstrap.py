"""Clean-volume proof that production can bootstrap without the development seed.

Uses Compose project atlas-bootstrap-proof and its own volumes. It does not
attach to the atlas or atlas-staging projects.
"""

from __future__ import annotations

import json
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
ENV_FILE = ROOT / "infrastructure" / "staging" / ".env.accept"
CA_FILE = ROOT / "infrastructure" / "staging" / "accept-ca.crt"
PROJECT = "atlas-bootstrap-proof"
FORBIDDEN_PROJECTS = {"atlas", "atlas-staging", "infrastructure", "titan", "legalstats"}
SECRET_KEYS = {
    "STAGING_SECRET_KEY",
    "STAGING_CREDENTIAL_ENCRYPTION_KEYS",
    "STAGING_POSTGRES_PASSWORD",
    "STAGING_N8N_ENCRYPTION_KEY",
    "ATLAS_BOOTSTRAP_PASSWORD",
}


class AcceptFailure(RuntimeError):
    pass


class PinnedHTTPSConnection(HTTPSConnection):
    def connect(self) -> None:
        raw = socket.create_connection(("127.0.0.1", self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def redact(text: str, env: dict[str, str]) -> str:
    redacted = text
    for key in SECRET_KEYS:
        secret = env.get(key, "")
        if len(secret) >= 8:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted


def compose(
    env: dict[str, str], *args: str, check: bool = True, stream: bool = False
) -> subprocess.CompletedProcess[str]:
    if PROJECT in FORBIDDEN_PROJECTS:
        raise AcceptFailure("protected_project")
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
    if not stream:
        result.stdout = redact(result.stdout or "", env)
        result.stderr = redact(result.stderr or "", env)
    if check and result.returncode != 0:
        raise AcceptFailure(f"{' '.join(args)} failed\n{result.stdout}\n{result.stderr}".strip())
    return result


def write_env() -> dict[str, str]:
    password = secrets.token_hex(24)
    values = {
        "STAGING_ENVIRONMENT": "production",
        "STAGING_SECRET_KEY": secrets.token_hex(32),
        "STAGING_CREDENTIAL_ENCRYPTION_KEYS": f"stage-01={secrets.token_hex(32)}",
        "STAGING_POSTGRES_USER": "atlas",
        "STAGING_POSTGRES_PASSWORD": secrets.token_hex(24),
        "STAGING_POSTGRES_DB": "atlas",
        "STAGING_N8N_ENCRYPTION_KEY": secrets.token_hex(32),
        "STAGING_HOST": "atlas.localhost",
        "STAGING_HTTP_PORT": "18080",
        "STAGING_HTTPS_PORT": "18443",
        "STAGING_CORS_ORIGINS": "https://atlas.localhost:18443",
        "STAGING_HOOK_KEY_ID": "",
        "STAGING_HOOK_SECRET": "",
        "ATLAS_BOOTSTRAP_PASSWORD": password,
    }
    ENV_FILE.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    return values


def wait_healthy(env: dict[str, str]) -> None:
    deadline = time.monotonic() + 180
    last = ""
    while time.monotonic() < deadline:
        result = compose(env, "ps", "--format", "json", check=False)
        last = result.stdout
        rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip().startswith("{")]
        states = {row.get("Service"): row.get("Health") or row.get("State") for row in rows}
        names = [row.get("Name", "") for row in rows]
        if any(not str(name).startswith(f"{PROJECT}-") for name in names):
            raise AcceptFailure("compose project attached to an unexpected container")
        if states.get("api") == "healthy" and states.get("web") == "healthy" and "n8n" in states:
            return
        time.sleep(2)
    raise AcceptFailure(f"stack did not become healthy\n{last}")


def assert_private_ports(env: dict[str, str]) -> None:
    for service, port in (
        ("postgres", "5432"),
        ("api", "8000"),
        ("mailpit", "8025"),
        ("n8n", "5678"),
        ("ollama", "11434"),
    ):
        result = compose(env, "port", service, port, check=False)
        if result.returncode == 0 and "invalid ip" not in result.stdout.lower():
            raise AcceptFailure(f"{service} port {port} is published at {result.stdout.strip()}")
    published = compose(env, "port", "caddy", "443")
    if ":18443" not in published.stdout:
        raise AcceptFailure(f"proof Caddy is not on 18443\n{published.stdout}")


def exec_api(env: dict[str, str], *command: str) -> subprocess.CompletedProcess[str]:
    return compose(env, "exec", "-T", "-u", "atlas", "api", *command)


def assert_production_boot(env: dict[str, str]) -> None:
    identity = exec_api(
        env,
        "python",
        "-c",
        "import os; url=os.environ['ATLAS_DATABASE_URL']; "
        "assert os.environ['ATLAS_ENVIRONMENT']=='production'; "
        "assert os.environ['ATLAS_PUBLIC_DEMO']=='false'; "
        "assert os.environ['ATLAS_COOKIE_SECURE']=='true'; "
        "assert 'SEED_ADMIN_PASSWORD' not in os.environ; "
        "assert '@postgres:5432/' in url; "
        "print('production_env_ok')",
    )
    if "production_env_ok" not in identity.stdout:
        raise AcceptFailure("API did not boot in production")
    current = exec_api(env, "alembic", "current")
    if "head" not in f"{current.stdout}\n{current.stderr}":
        raise AcceptFailure(f"migrations are not at head\n{current.stdout}\n{current.stderr}")
    status = exec_api(env, "python", "-m", "app.scripts.bootstrap", "--status")
    if "users=0 organizations=0 administrators=0 companies=0" not in status.stdout:
        raise AcceptFailure(f"database was not empty\n{status.stdout}")
    user = exec_api(env, "python", "-c", "import os; print(os.getuid())")
    if user.stdout.strip() != "10001":
        raise AcceptFailure(f"API exec uid is {user.stdout.strip()}")


def bootstrap(env: dict[str, str], password: str) -> subprocess.CompletedProcess[str]:
    payload = {
        "organization_name": "Harbor Proof",
        "organization_slug": "harbor-proof",
        "email": "admin@harbor-proof.example",
        "full_name": "Proof Admin",
        "password": password,
    }
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
        "exec",
        "-T",
        "-u",
        "atlas",
        "api",
        "python",
        "-m",
        "app.scripts.bootstrap",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    result.stdout = redact(result.stdout, env)
    result.stderr = redact(result.stderr, env)
    if password in f"{result.stdout}\n{result.stderr}":
        raise AcceptFailure("bootstrap printed the password")
    return result


def copy_ca(env: dict[str, str]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = compose(
            env,
            "cp",
            "caddy:/data/caddy/pki/authorities/local/root.crt",
            str(CA_FILE),
            check=False,
        )
        if result.returncode == 0 and CA_FILE.is_file():
            return
        time.sleep(2)
    raise AcceptFailure("Caddy CA was not available")


def login(password: str) -> None:
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(CA_FILE))
    body = json.dumps(
        {"email": "admin@harbor-proof.example", "password": password}
    ).encode()
    connection = PinnedHTTPSConnection("atlas.localhost", 18443, context=context, timeout=30)
    try:
        connection.request(
            "POST",
            "/api/v1/auth/login",
            body=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read()
        cookies = response.headers.get_all("Set-Cookie") or []
    finally:
        connection.close()
    if response.status != 200:
        raise AcceptFailure(f"HTTPS login failed: {response.status}")
    session = next((item for item in cookies if item.lower().startswith("atlas_session=")), "")
    lowered = session.lower()
    for flag in ("httponly", "secure", "samesite=lax"):
        if flag not in lowered:
            raise AcceptFailure(f"session cookie is missing {flag}")
    if "domain=" in lowered:
        raise AcceptFailure("session cookie sets Domain")
    payload = json.loads(raw.decode())
    if not payload.get("csrf_token"):
        raise AcceptFailure("login response has no csrf token")


def provision(env: dict[str, str]) -> str:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "infrastructure" / "staging" / "provision_n8n.py"),
            "--project",
            PROJECT,
            "--env-file",
            str(ENV_FILE),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    output = redact(f"{result.stdout}\n{result.stderr}", env)
    if result.returncode != 0:
        raise AcceptFailure(f"n8n provisioning failed\n{output}")
    return output


def main() -> int:
    if PROJECT in FORBIDDEN_PROJECTS:
        raise AcceptFailure("protected_project")
    env = write_env()
    password = env["ATLAS_BOOTSTRAP_PASSWORD"]
    try:
        compose(env, "down", "-v", "--remove-orphans", check=False)
        print("Building the disposable proof stack")
        compose(env, "up", "-d", "--build", stream=True)
        wait_healthy(env)
        assert_private_ports(env)
        assert_production_boot(env)
        created = bootstrap(env, password)
        if created.returncode != 0 or "bootstrap_ok" not in created.stdout:
            raise AcceptFailure(f"bootstrap failed\n{created.stdout}\n{created.stderr}")
        if "slug=harbor-proof" not in created.stdout:
            raise AcceptFailure("bootstrap did not report the organization")
        repeated = bootstrap(env, secrets.token_hex(24))
        if repeated.returncode == 0 or "administrator_exists" not in repeated.stdout:
            raise AcceptFailure(f"repeat bootstrap was accepted\n{repeated.stdout}")
        status = exec_api(env, "python", "-m", "app.scripts.bootstrap", "--status")
        if "users=1 organizations=1 administrators=1 companies=0" not in status.stdout:
            raise AcceptFailure(f"unexpected records after bootstrap\n{status.stdout}")
        copy_ca(env)
        login(password)
        print("https_login_ok https://atlas.localhost:18443")
        first = provision(env)
        if "provision_ok" not in first or "imported=2" not in first:
            raise AcceptFailure(f"first import did not install both workflows\n{first}")
        second = provision(env)
        if "imported=0" not in second or "existing=2" not in second or "active=0" not in second:
            raise AcceptFailure(f"second import was not idempotent\n{second}")
        print(first.strip())
        print(second.strip())
        print("bootstrap_proof_ok")
        return 0
    finally:
        compose(env, "down", "-v", "--remove-orphans", check=False)
        ENV_FILE.unlink(missing_ok=True)
        CA_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AcceptFailure as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
