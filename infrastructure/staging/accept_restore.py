"""Prove a backup restores onto fresh volumes without touching live projects.

Uses Compose project atlas-backup-proof. It does not attach to atlas or
atlas-staging, and it deletes its own volumes when it finishes.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import time
import uuid
from http.client import HTTPSConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "infrastructure" / "compose.staging.yaml"
ENV_FILE = ROOT / "infrastructure" / "staging" / ".env.backup-proof"
CA_FILE = ROOT / "infrastructure" / "staging" / "backup-proof-ca.crt"
BACKUP_DIR = ROOT / "infrastructure" / "staging" / "backups" / "proof"
PROJECT = "atlas-backup-proof"
HTTP_PORT = "28080"
HTTPS_PORT = "28443"
DOCUMENT = (
    b"Harbor Proof Yard stores bonded pallets under invoice code RESTORE-1842.\n"
    b"The March warehouse transfer is covered by that same invoice.\n"
)
QUERY = "Which invoice covers the bonded pallets?"
COMPANY = "Restore Proof Yard"
CREDENTIAL_NAME = "restore-proof"
FORBIDDEN = {"atlas", "atlas-staging", "infrastructure", "titan", "legalstats"}


class AcceptFailure(RuntimeError):
    pass


class PinnedHTTPSConnection(HTTPSConnection):
    def connect(self) -> None:
        raw = socket.create_connection(("127.0.0.1", self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def redact(text: str, env: dict[str, str]) -> str:
    redacted = text
    for key in (
        "STAGING_SECRET_KEY",
        "STAGING_POSTGRES_PASSWORD",
        "STAGING_N8N_ENCRYPTION_KEY",
        "ATLAS_BOOTSTRAP_PASSWORD",
        "ATLAS_BACKUP_PASSPHRASE",
        "CREDENTIAL_VALUE",
    ):
        secret = env.get(key, "")
        if len(secret) >= 8:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted


def compose(
    env: dict[str, str],
    *args: str,
    check: bool = True,
    stdin: bytes | None = None,
    redact_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    if PROJECT in FORBIDDEN:
        raise AcceptFailure("protected_project")
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            PROJECT,
            "--project-directory",
            str(ROOT / "infrastructure"),
            "--env-file",
            str(ENV_FILE.resolve()),
            "-f",
            str(COMPOSE_FILE),
            *args,
        ],
        cwd=ROOT,
        input=stdin,
        text=stdin is None,
        capture_output=True,
        check=False,
    )
    stdout = (
        result.stdout
        if isinstance(result.stdout, str)
        else result.stdout.decode("utf-8", "replace")
    )
    stderr = (
        result.stderr
        if isinstance(result.stderr, str)
        else result.stderr.decode("utf-8", "replace")
    )
    if redact_output:
        stdout, stderr = redact(stdout, env), redact(stderr, env)
    if check and result.returncode != 0:
        raise AcceptFailure(f"{' '.join(args)} failed\n{stdout}\n{stderr}".strip())
    return subprocess.CompletedProcess(args, result.returncode, stdout, stderr)


def write_env() -> dict[str, str]:
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    password = secrets.token_hex(24)
    values = {
        # This disposable proof uses the deterministic provider so it does not
        # download Ollama. Production correctly rejects deterministic providers;
        # the real staging configuration is unchanged.
        "STAGING_ENVIRONMENT": "development",
        "STAGING_SECRET_KEY": secrets.token_hex(32),
        "STAGING_POSTGRES_USER": "atlas",
        "STAGING_POSTGRES_PASSWORD": secrets.token_hex(24),
        "STAGING_POSTGRES_DB": "atlas",
        "STAGING_N8N_ENCRYPTION_KEY": secrets.token_hex(32),
        "STAGING_HOST": "atlas.localhost",
        "STAGING_HTTP_PORT": HTTP_PORT,
        "STAGING_HTTPS_PORT": HTTPS_PORT,
        "STAGING_CORS_ORIGINS": f"https://atlas.localhost:{HTTPS_PORT}",
        # The acceptance proof validates restored vectors and retrieval without
        # downloading a model. It deliberately uses the deterministic 768-wide
        # test provider; production/staging defaults remain unchanged.
        "STAGING_EMBEDDING_PROVIDER": "double",
        "STAGING_EMBEDDING_MODEL": "restore-proof-deterministic",
        "STAGING_EMBEDDING_DIMENSIONS": "768",
        "STAGING_HOOK_KEY_ID": "",
        "STAGING_HOOK_SECRET": "",
        "ATLAS_BOOTSTRAP_PASSWORD": password,
        "ATLAS_BACKUP_PASSPHRASE": secrets.token_hex(32),
        "CREDENTIAL_VALUE": secrets.token_hex(16),
    }
    ENV_FILE.write_text(
        "".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8"
    )
    if not ENV_FILE.is_file():
        raise AcceptFailure("backup_proof_env_not_created")
    return values


def marker(container: str) -> str:
    inspected = subprocess.run(
        ["docker", "inspect", "-f", "{{.Id}} {{.State.StartedAt}}", container],
        text=True,
        capture_output=True,
        check=False,
    )
    if inspected.returncode != 0:
        return f"absent {container}"
    counts = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            "atlas",
            "-d",
            "atlas",
            "-At",
            "-c",
            "select (select count(*) from documents), (select count(*) from chunks), "
            "(select count(*) from companies), (select count(*) from users)",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    count_line = counts.stdout.strip() if counts.returncode == 0 else "unavailable"
    return f"{container} {inspected.stdout.strip()} {count_line}"


def live_markers() -> str:
    return "\n".join(
        marker(name)
        for name in ("atlas-postgres-1", "atlas-staging-postgres-1", "atlas-staging-n8n-1")
    )


def wait_healthy(env: dict[str, str]) -> None:
    deadline = time.monotonic() + 300
    last = ""
    while time.monotonic() < deadline:
        result = compose(env, "ps", "--format", "json", check=False)
        last = result.stdout
        rows = [
            json.loads(line) for line in result.stdout.splitlines() if line.strip().startswith("{")
        ]
        states = {row.get("Service"): row.get("Health") or row.get("State") for row in rows}
        names = [str(row.get("Name", "")) for row in rows]
        if any(not name.startswith(f"{PROJECT}-") for name in names):
            raise AcceptFailure("compose project attached to an unexpected container")
        if states.get("api") == "healthy" and states.get("web") == "healthy":
            return
        time.sleep(2)
    diagnostics = compose(
        env,
        "logs",
        "--no-color",
        "api",
        "postgres",
        "embedding-model",
        check=False,
    )
    detail = (diagnostics.stdout + diagnostics.stderr)[-4000:]
    raise AcceptFailure(f"stack did not become healthy\n{last}\n{detail}")


def bootstrap(env: dict[str, str]) -> str:
    payload = json.dumps(
        {
            "organization_name": "Harbor Proof",
            "organization_slug": "harbor-proof",
            "email": "admin@harbor-proof.example",
            "full_name": "Proof Admin",
            "password": env["ATLAS_BOOTSTRAP_PASSWORD"],
        }
    ).encode()
    result = compose(
        env,
        "exec",
        "-T",
        "-u",
        "atlas",
        "api",
        "python",
        "-m",
        "app.scripts.bootstrap",
        stdin=payload,
    )
    if "bootstrap_ok" not in result.stdout or env["ATLAS_BOOTSTRAP_PASSWORD"] in result.stdout:
        raise AcceptFailure(f"bootstrap failed\n{result.stdout}\n{result.stderr}")
    return result.stdout


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


class ApiClient:
    def __init__(self, password: str) -> None:
        self.password = password
        self.cookie = ""
        self.csrf = ""
        self.organization_id = ""

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        context = ssl.create_default_context()
        context.load_verify_locations(cafile=str(CA_FILE))
        connection = PinnedHTTPSConnection(
            "atlas.localhost", int(HTTPS_PORT), context=context, timeout=60
        )
        sent = {"Accept": "application/json"}
        if self.cookie:
            sent["Cookie"] = self.cookie
        if headers:
            sent.update(headers)
        try:
            connection.request(method, path, body=body, headers=sent)
            response = connection.getresponse()
            payload = response.read()
            header_map = {key.lower(): value for key, value in response.headers.items()}
            cookies = response.headers.get_all("Set-Cookie") or []
        finally:
            connection.close()
        session = next((item for item in cookies if item.lower().startswith("atlas_session=")), "")
        if session:
            self.cookie = session.split(";", 1)[0]
        return response.status, header_map, payload

    def login(self) -> None:
        status, _, payload = self.request(
            "POST",
            "/api/v1/auth/login",
            json.dumps({"email": "admin@harbor-proof.example", "password": self.password}).encode(),
            {"Content-Type": "application/json"},
        )
        if status != 200:
            raise AcceptFailure(f"login failed: {status}")
        parsed = json.loads(payload.decode())
        self.csrf = parsed["csrf_token"]
        self.organization_id = parsed["memberships"][0]["organization_id"]
        if not self.cookie:
            raise AcceptFailure("login did not set a session cookie")

    def upload(self) -> str:
        boundary = "atlasproofboundary"
        body = (
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="restore-proof.txt"\r\n'
                f"Content-Type: text/plain\r\n\r\n"
            ).encode()
            + DOCUMENT
            + f"\r\n--{boundary}--\r\n".encode()
        )
        status, _, payload = self.request(
            "POST",
            f"/api/v1/organizations/{self.organization_id}/documents",
            body,
            {
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-CSRF-Token": self.csrf,
            },
        )
        if status != 201:
            raise AcceptFailure(f"upload failed: {status} {payload[:200]!r}")
        return str(json.loads(payload.decode())["id"])

    def wait_ready(self, document_id: str) -> None:
        deadline = time.monotonic() + 180
        last = ""
        while time.monotonic() < deadline:
            status, _, payload = self.request(
                "GET",
                f"/api/v1/organizations/{self.organization_id}/documents/{document_id}",
            )
            last = payload.decode("utf-8", "replace")
            if status == 200 and json.loads(last)["status"] == "ready":
                return
            if status == 200 and json.loads(last)["status"] == "failed":
                raise AcceptFailure(f"indexing failed\n{last}")
            time.sleep(2)
        raise AcceptFailure(f"document did not become ready\n{last}")

    def search(self) -> None:
        query = QUERY.replace(" ", "%20")
        status, _, payload = self.request(
            "GET",
            f"/api/v1/organizations/{self.organization_id}/documents/search?q={query}",
        )
        if status != 200 or b"RESTORE-1842" not in payload:
            raise AcceptFailure(f"search failed: {status} {payload[:300]!r}")

    def create_company(self) -> None:
        status, _, payload = self.request(
            "POST",
            f"/api/v1/organizations/{self.organization_id}/companies",
            json.dumps({"name": COMPANY}).encode(),
            {"Content-Type": "application/json", "X-CSRF-Token": self.csrf},
        )
        if status != 201:
            raise AcceptFailure(f"company create failed: {status} {payload[:200]!r}")

    def isolation(self) -> None:
        status, _, payload = self.request(
            "GET",
            f"/api/v1/organizations/{uuid.uuid4()}/companies",
        )
        if status != 404 or b"not_found" not in payload:
            raise AcceptFailure(f"organization isolation failed: {status}")


def import_credential(env: dict[str, str]) -> None:
    document = json.dumps(
        [
            {
                "id": "restoreproof0001",
                "name": CREDENTIAL_NAME,
                "type": "httpHeaderAuth",
                "data": {"name": "X-Atlas-Proof", "value": env["CREDENTIAL_VALUE"]},
            }
        ]
    ).encode()
    result = compose(
        env,
        "exec",
        "-T",
        "n8n",
        "sh",
        "-c",
        "cat > /home/node/credential.json && "
        "n8n import:credentials --input=/home/node/credential.json && "
        "rm -f /home/node/credential.json",
        stdin=document,
    )
    if result.returncode != 0:
        raise AcceptFailure(f"credential import failed\n{result.stdout}\n{result.stderr}")


def export_credentials(env: dict[str, str]) -> str:
    result = compose(
        env,
        "exec",
        "-T",
        "n8n",
        "sh",
        "-c",
        "n8n export:credentials --all --decrypted "
        "--output=/home/node/credentials-export.json >/dev/null && "
        "cat /home/node/credentials-export.json && "
        "rm -f /home/node/credentials-export.json",
        redact_output=False,
    )
    return result.stdout


def run_script(env: dict[str, str], script: str, *args: str) -> str:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "infrastructure" / "staging" / script), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "ATLAS_BACKUP_PASSPHRASE": env["ATLAS_BACKUP_PASSPHRASE"]},
    )
    output = redact(f"{completed.stdout}\n{completed.stderr}", env)
    if completed.returncode != 0:
        raise AcceptFailure(f"{script} failed\n{output}")
    if env["ATLAS_BACKUP_PASSPHRASE"] in output or env["CREDENTIAL_VALUE"] in output:
        raise AcceptFailure(f"{script} printed a secret")
    return output


def sql(env: dict[str, str], statement: str) -> str:
    result = compose(
        env,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "atlas",
        "-d",
        "atlas",
        "-At",
        "-c",
        statement,
    )
    return result.stdout.strip()


def stored_file_sha(env: dict[str, str]) -> str:
    path = sql(env, "select storage_path from documents")
    result = compose(
        env,
        "run",
        "-T",
        "--rm",
        "--no-deps",
        "--user",
        "10001",
        "--entrypoint",
        "python",
        "api",
        "-c",
        "import hashlib, pathlib, sys; "
        "print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())",
        path,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def assert_restored_rows(env: dict[str, str], digest: str) -> None:
    dims = sql(
        env,
        "select count(*), min(vector_dims(embedding_768)), "
        "max(vector_dims(embedding_768)) from chunks",
    )
    count, low, high = (dims.split("|") + ["", ""])[:3]
    if count in {"", "0"} or low != "768" or high != "768":
        raise AcceptFailure(f"restored vectors are {dims}")
    if sql(env, "select name from companies") != COMPANY:
        raise AcceptFailure("restored company did not match")
    if sql(env, "select status from documents") != "ready":
        raise AcceptFailure("restored document was not ready")
    if stored_file_sha(env) != digest:
        raise AcceptFailure("restored file bytes did not match")


def wrong_key_cannot_read(env: dict[str, str]) -> None:
    wrong = secrets.token_hex(32)
    result = subprocess.run(
        [
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
            "run",
            "-T",
            "--rm",
            "--no-deps",
            "-e",
            f"N8N_ENCRYPTION_KEY={wrong}",
            "--entrypoint",
            "n8n",
            "n8n",
            "export:credentials",
            "--all",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    output = f"{result.stdout}\n{result.stderr}"
    leaked = result.returncode == 0 and (
        env["CREDENTIAL_VALUE"] in output or CREDENTIAL_NAME in output
    )
    if leaked:
        raise AcceptFailure("n8n read the credential with a different encryption key")


def provision(env: dict[str, str]) -> None:
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
    if result.returncode != 0 or "imported=2" not in output:
        raise AcceptFailure(f"n8n import failed\n{output}")


def main() -> int:
    if PROJECT in FORBIDDEN:
        raise AcceptFailure("protected_project")
    before = live_markers()
    env = write_env()
    failed = False
    try:
        compose(env, "down", "-v", "--remove-orphans", check=False)
        print("Building the disposable backup proof")
        startup = compose(env, "up", "-d", "--build", check=False)
        if startup.returncode != 0 and "dependency failed to start" not in startup.stderr:
            raise AcceptFailure(f"disposable startup failed\n{startup.stdout}\n{startup.stderr}")
        wait_healthy(env)
        bootstrap(env)
        copy_ca(env)
        client = ApiClient(env["ATLAS_BOOTSTRAP_PASSWORD"])
        client.login()
        document_id = client.upload()
        client.wait_ready(document_id)
        client.search()
        client.create_company()
        provision(env)
        import_credential(env)
        original_credentials = export_credentials(env)
        if (
            CREDENTIAL_NAME not in original_credentials
            or env["CREDENTIAL_VALUE"] not in original_credentials
        ):
            raise AcceptFailure("n8n did not store the proof credential")
        digest = hashlib.sha256(DOCUMENT).hexdigest()
        if stored_file_sha(env) != digest:
            raise AcceptFailure("uploaded bytes were not stored")
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup_output = run_script(
            env,
            "backup.py",
            "--project",
            PROJECT,
            "--env-file",
            str(ENV_FILE),
            "--backup-dir",
            str(BACKUP_DIR),
            "--keep",
            "14",
        )
        if "backup_ok" not in backup_output or "encrypted=true" not in backup_output:
            raise AcceptFailure(f"backup did not finish\n{backup_output}")
        archives = list(BACKUP_DIR.glob("atlas-*.tar.gz.enc"))
        if len(archives) != 1:
            raise AcceptFailure(f"expected one encrypted archive, found {len(archives)}")
        archive_bytes = archives[0].read_bytes()
        for secret in (
            env["ATLAS_BACKUP_PASSPHRASE"],
            env["CREDENTIAL_VALUE"],
            env["STAGING_N8N_ENCRYPTION_KEY"],
        ):
            if secret.encode() in archive_bytes:
                raise AcceptFailure("encrypted archive contains a plaintext secret")
        compose(env, "down", "-v", "--remove-orphans")
        if live_markers() != before:
            raise AcceptFailure("live projects changed while the proof volumes were removed")
        started = time.monotonic()
        restore_output = run_script(
            env,
            "restore.py",
            "--project",
            PROJECT,
            "--env-file",
            str(ENV_FILE),
            "--archive",
            str(archives[0]),
        )
        data_seconds = round(time.monotonic() - started, 1)
        if "restore_ok" not in restore_output:
            raise AcceptFailure(f"restore did not finish\n{restore_output}")
        assert_restored_rows(env, digest)
        compose(env, "up", "-d")
        wait_healthy(env)
        copy_ca(env)
        ready_seconds = round(time.monotonic() - started, 1)
        restored = ApiClient(env["ATLAS_BOOTSTRAP_PASSWORD"])
        restored.login()
        restored.search()
        restored.isolation()
        verified_seconds = round(time.monotonic() - started, 1)
        if restored.organization_id != client.organization_id:
            raise AcceptFailure("restored organization id changed")
        companies = restored.request(
            "GET", f"/api/v1/organizations/{restored.organization_id}/companies"
        )
        if companies[0] != 200 or COMPANY.encode() not in companies[2]:
            raise AcceptFailure("restored API did not return the company")
        restored_credentials = export_credentials(env)
        if (
            CREDENTIAL_NAME not in restored_credentials
            or env["CREDENTIAL_VALUE"] not in restored_credentials
        ):
            raise AcceptFailure("restored n8n credential did not decrypt with the original key")
        wrong_key_cannot_read(env)
        workflows = compose(env, "exec", "-T", "n8n", "n8n", "export:workflow", "--all")
        if (
            "ATLAS Lead Processing" not in workflows.stdout
            or "ATLAS Follow-up" not in workflows.stdout
        ):
            raise AcceptFailure("restored n8n workflows were missing")
        print(
            f"restore_measured data_s={data_seconds} ready_s={ready_seconds} "
            f"verified_s={verified_seconds}"
        )
        print(backup_output.strip())
        print("backup_restore_proof_ok")
    except AcceptFailure as exc:
        print(str(exc), file=sys.stderr)
        failed = True
    finally:
        compose(env, "down", "-v", "--remove-orphans", check=False)
        ENV_FILE.unlink(missing_ok=True)
        CA_FILE.unlink(missing_ok=True)
        shutil.rmtree(BACKUP_DIR, ignore_errors=True)
        changed = live_markers() != before
    if changed:
        print("staging_changed", file=sys.stderr)
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AcceptFailure as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
