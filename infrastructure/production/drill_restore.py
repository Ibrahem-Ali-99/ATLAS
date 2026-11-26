"""Prove backup, restore, and one migration rollback on disposable Postgres.

Creates only containers, volumes, and networks whose names start with
atlas-prod-drill. It does not attach to the development or staging projects
and removes its own resources when it finishes.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import socket
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "infrastructure" / "staging"
sys.path.insert(0, str(STAGING))

from backup import CIPHER_PROGRAM  # noqa: E402
from backup_contract import dump_command, restore_command  # noqa: E402
from isolation import assert_owned, live_markers  # noqa: E402

COMPOSE_FILE = ROOT / "infrastructure" / "compose.production.yaml"
RESULT = ROOT / "var" / "production-drill" / "restore.json"
PROJECT = "atlas-prod-drill"
NETWORK = "atlas-prod-drill"
PG_VOLUME = "atlas-prod-drill-pgdata"
UPLOAD_VOLUME = "atlas-prod-drill-uploads"
RESTORED_PG = "atlas-prod-drill-pgdata-restored"
RESTORED_UPLOADS = "atlas-prod-drill-uploads-restored"
SOURCE = "atlas-prod-drill-pg"
RESTORED = "atlas-prod-drill-pg-restored"
UPLOAD_BYTES = b"atlas-upload-proof-v1\n"
PROOF_NOTE = "restore-proof-token"


def redact(text: str, secret: str) -> str:
    if secret and len(secret) >= 8:
        return text.replace(secret, "[redacted]")
    return text


def run(command: list[str], secret: str, **kwargs) -> subprocess.CompletedProcess[bytes]:
    for part in command:
        token = part.split(":", 1)[0]
        if token.startswith("atlas-"):
            assert_owned(token)
    return subprocess.run(command, capture_output=True, check=False, **kwargs)


def owned_remove(kind: str, name: str) -> None:
    assert_owned(name)
    if kind == "container":
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
    elif kind == "volume":
        subprocess.run(["docker", "volume", "rm", "-f", name], capture_output=True, check=False)
    elif kind == "network":
        subprocess.run(["docker", "network", "rm", name], capture_output=True, check=False)


def cleanup(secret: str) -> None:
    subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            PROJECT,
            "--project-directory",
            str(COMPOSE_FILE.parent),
            "-f",
            str(COMPOSE_FILE),
            "--env-file",
            str(ROOT / "var" / "production-drill" / "compose.env"),
            "down",
            "-v",
            "--remove-orphans",
        ],
        capture_output=True,
        check=False,
    )
    for name in (SOURCE, RESTORED):
        owned_remove("container", name)
    for name in (PG_VOLUME, UPLOAD_VOLUME, RESTORED_PG, RESTORED_UPLOADS):
        owned_remove("volume", name)
    owned_remove("network", NETWORK)
    env_file = ROOT / "var" / "production-drill" / "compose.env"
    if env_file.exists():
        env_file.write_text("", encoding="utf-8")
        env_file.unlink(missing_ok=True)
    del secret


def free_port() -> int:
    for port in (55432, 55434, 55436, 55438):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("no free loopback port for the disposable database")


def wait_ready(container: str, secret: str) -> bool:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        result = run(
            ["docker", "exec", container, "pg_isready", "-U", "atlas", "-d", "atlas"],
            secret,
        )
        if result.returncode == 0:
            return True
        time.sleep(2)
    return False


def psql(container: str, sql: str, secret: str) -> str:
    result = run(
        ["docker", "exec", "-i", container, "psql", "-U", "atlas", "-d", "atlas", "-At", "-v", "ON_ERROR_STOP=1"],
        secret,
        input=sql.encode(),
    )
    if result.returncode != 0:
        detail = redact(result.stderr.decode("utf-8", "replace"), secret)
        raise RuntimeError(detail[:300] or "psql_failed")
    return result.stdout.decode("utf-8", "replace").strip()


def alembic(direction: str, url: str, secret: str) -> str:
    env = os.environ.copy()
    env["ALEMBIC_DATABASE_URL"] = url
    env["ATLAS_DATABASE_URL"] = url
    env["ATLAS_SECRET_KEY"] = "d" * 48
    result = subprocess.run(
        ["uv", "run", "--frozen", "alembic", *direction.split()],
        cwd=ROOT / "apps" / "api",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = redact(result.stderr + result.stdout, secret)
        raise RuntimeError(detail[-400:] or "alembic_failed")
    return redact(result.stdout, secret)


def seal(payload: bytes, passphrase: str, mode: str) -> bytes:
    result = subprocess.run(
        [sys.executable, "-c", CIPHER_PROGRAM, mode],
        input=payload,
        capture_output=True,
        env={**os.environ, "ATLAS_BACKUP_PASSPHRASE": passphrase},
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError("cipher_failed")
    return result.stdout


def compose_env(password: str) -> str:
    secret = secrets.token_hex(32)
    values = {
        "PRODUCTION_SECRET_KEY": secret,
        "PRODUCTION_CREDENTIAL_ENCRYPTION_KEYS": f"prod-01={secrets.token_hex(32)}",
        "PRODUCTION_POSTGRES_USER": "atlas",
        "PRODUCTION_POSTGRES_PASSWORD": password,
        "PRODUCTION_POSTGRES_DB": "atlas",
        "PRODUCTION_N8N_ENCRYPTION_KEY": secrets.token_hex(32),
        "PRODUCTION_HOST": "atlas.localhost",
        "PRODUCTION_HTTP_PORT": "19080",
        "PRODUCTION_HTTPS_PORT": "19443",
        "PRODUCTION_CORS_ORIGINS": "https://atlas.localhost:19443",
        "PRODUCTION_CAMPAIGN_PUBLIC_URL": "https://atlas.localhost:19443",
        "PRODUCTION_LLM_PROVIDER": "groq",
        "PRODUCTION_LLM_API_KEY": secrets.token_hex(24),
        "PRODUCTION_LLM_MODEL": "llama-3.3-70b-versatile",
    }
    return "".join(f"{key}={value}\n" for key, value in values.items())


def prove_compose_postgres(password: str) -> dict[str, object]:
    env_path = ROOT / "var" / "production-drill" / "compose.env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(compose_env(password), encoding="utf-8")
    command = [
        "docker",
        "compose",
        "--project-name",
        PROJECT,
        "--project-directory",
        str(COMPOSE_FILE.parent),
        "-f",
        str(COMPOSE_FILE),
        "--env-file",
        str(env_path),
    ]
    started = run([*command, "up", "-d", "--no-deps", "postgres"], password)
    if started.returncode != 0:
        detail = redact(started.stderr.decode("utf-8", "replace"), password)
        raise RuntimeError(detail[-400:] or "postgres_compose_failed")
    container = f"{PROJECT}-postgres-1"
    assert_owned(container)
    if not wait_ready(container, password):
        raise RuntimeError("compose postgres did not become ready")
    deadline = time.monotonic() + 40
    status = ""
    while time.monotonic() < deadline:
        health = run(
            ["docker", "inspect", "-f", "{{if .State.Health}}{{.State.Health.Status}}{{end}}", container],
            password,
        )
        status = health.stdout.decode().strip()
        if status == "healthy":
            break
        time.sleep(2)
    if status != "healthy":
        raise RuntimeError("production postgres health check did not pass")
    ports = run(
        ["docker", "inspect", "-f", "{{json .NetworkSettings.Ports}}", container],
        password,
    )
    published = ports.stdout.decode("utf-8", "replace")
    if "HostPort" in published:
        raise RuntimeError("production postgres published a host port")
    stopped = run([*command, "down", "-v", "--remove-orphans"], password)
    if stopped.returncode != 0:
        raise RuntimeError("compose drill cleanup failed")
    return {"compose_postgres_healthy": True, "compose_postgres_unpublished": True}


def start_postgres(container: str, volume: str, port: int, password: str) -> None:
    assert_owned(container)
    assert_owned(volume)
    created = run(["docker", "volume", "create", volume], password)
    if created.returncode != 0:
        raise RuntimeError("volume_create_failed")
    started = run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container,
            "--network",
            NETWORK,
            "-p",
            f"127.0.0.1:{port}:5432",
            "-e",
            "POSTGRES_USER=atlas",
            "-e",
            f"POSTGRES_PASSWORD={password}",
            "-e",
            "POSTGRES_DB=atlas",
            "-v",
            f"{volume}:/var/lib/postgresql/data",
            "pgvector/pgvector:pg17",
        ],
        password,
    )
    if started.returncode != 0 or not wait_ready(container, password):
        raise RuntimeError("disposable postgres did not become ready")


def write_upload(volume: str, password: str) -> str:
    assert_owned(volume)
    run(["docker", "volume", "create", volume], password)
    quoted = repr(UPLOAD_BYTES)
    result = run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume}:/data",
            "python:3.12-slim",
            "python",
            "-c",
            f"open('/data/proof.bin','wb').write({quoted})",
        ],
        password,
    )
    if result.returncode != 0:
        raise RuntimeError("upload_write_failed")
    return hashlib.sha256(UPLOAD_BYTES).hexdigest()


def read_upload(volume: str, password: str) -> str:
    assert_owned(volume)
    result = run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume}:/data:ro",
            "python:3.12-slim",
            "python",
            "-c",
            "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('/data/proof.bin').read_bytes()).hexdigest())",
        ],
        password,
    )
    if result.returncode != 0:
        raise RuntimeError("upload_read_failed")
    return result.stdout.decode().strip()


def dump_database(container: str, password: str) -> bytes:
    result = run(["docker", "exec", "-i", container, *dump_command("atlas", "atlas")], password)
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError("pg_dump_failed")
    return result.stdout


def restore_database(container: str, payload: bytes, password: str) -> None:
    result = run(
        ["docker", "exec", "-i", container, *restore_command("atlas", "atlas", clean=False)],
        password,
        input=payload,
    )
    if result.returncode != 0:
        detail = redact(result.stderr.decode("utf-8", "replace"), password)
        raise RuntimeError(detail[-300:] or "pg_restore_failed")


def prove_dump_and_restore(password: str, passphrase: str, port: int) -> dict[str, object]:
    run(["docker", "network", "create", NETWORK], password)
    start_postgres(SOURCE, PG_VOLUME, port, password)
    url = f"postgresql+psycopg://atlas:{password}@127.0.0.1:{port}/atlas"
    alembic("upgrade head", url, password)
    head = psql(SOURCE, "SELECT version_num FROM alembic_version", password)
    alembic("downgrade -1", url, password)
    rolled = psql(SOURCE, "SELECT version_num FROM alembic_version", password)
    if rolled == head:
        raise RuntimeError("downgrade did not move the revision")
    alembic("upgrade head", url, password)
    restored_head = psql(SOURCE, "SELECT version_num FROM alembic_version", password)
    if restored_head != head:
        raise RuntimeError("upgrade did not return to the previous head")
    psql(
        SOURCE,
        "CREATE TABLE atlas_restore_proof (id int primary key, note text not null); "
        f"INSERT INTO atlas_restore_proof VALUES (1, '{PROOF_NOTE}');",
        password,
    )
    digest = write_upload(UPLOAD_VOLUME, password)
    if read_upload(UPLOAD_VOLUME, password) != digest:
        raise RuntimeError("upload_write_mismatch")
    dump = dump_database(SOURCE, password)
    upload_tar = tar_bytes({"proof.bin": UPLOAD_BYTES})
    plain = pack_archive({"postgres-atlas.dump": dump, "uploads.tar": upload_tar})
    encrypted = seal(plain, passphrase, "enc")
    opened = seal(encrypted, passphrase, "dec")
    if opened != plain:
        raise RuntimeError("decrypted archive did not match")
    owned_remove("container", SOURCE)
    owned_remove("volume", PG_VOLUME)
    owned_remove("volume", UPLOAD_VOLUME)
    if volume_exists(PG_VOLUME) or volume_exists(UPLOAD_VOLUME):
        raise RuntimeError("source volumes were not removed")
    time.sleep(1)
    start_postgres(RESTORED, RESTORED_PG, port, password)
    psql(RESTORED, "DROP SCHEMA public CASCADE; CREATE SCHEMA public;", password)
    restore_database(RESTORED, dump, password)
    note = psql(RESTORED, "SELECT note FROM atlas_restore_proof WHERE id = 1", password)
    version = psql(RESTORED, "SELECT version_num FROM alembic_version", password)
    run(["docker", "volume", "create", RESTORED_UPLOADS], password)
    extract_tar(RESTORED_UPLOADS, upload_tar, password)
    return {
        "migration_head": head,
        "migration_downgrade": rolled,
        "migration_restored_head": restored_head,
        "row_restored": note == PROOF_NOTE,
        "revision_restored": version == head,
        "upload_sha256_match": read_upload(RESTORED_UPLOADS, password) == digest,
        "archive_encrypted": encrypted.startswith(b"ATLAS1"),
    }


def volume_exists(name: str) -> bool:
    assert_owned(name)
    result = subprocess.run(["docker", "volume", "inspect", name], capture_output=True, check=False)
    return result.returncode == 0


def tar_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, payload in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def pack_archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, payload in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def extract_tar(volume: str, payload: bytes, password: str) -> None:
    assert_owned(volume)
    result = run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "-v",
            f"{volume}:/data",
            "python:3.12-slim",
            "tar",
            "-C",
            "/data",
            "-xf",
            "-",
        ],
        password,
        input=payload,
    )
    if result.returncode != 0:
        raise RuntimeError("upload_extract_failed")


def main() -> int:
    try:
        import cryptography  # noqa: F401
    except ImportError:
        print("drill_failed cryptography_missing")
        return 2
    password = secrets.token_hex(24)
    passphrase = secrets.token_hex(32)
    before = live_markers()
    report: dict[str, object] = {}
    try:
        port = free_port()
        report.update(prove_compose_postgres(password))
        report.update(prove_dump_and_restore(password, passphrase, port))
        after = live_markers()
        report["live_projects_unchanged"] = before == after
        ok = (
            report["compose_postgres_healthy"] is True
            and report["row_restored"] is True
            and report["upload_sha256_match"] is True
            and report["revision_restored"] is True
            and report["archive_encrypted"] is True
            and report["live_projects_unchanged"] is True
            and report["migration_downgrade"] != report["migration_head"]
        )
        report["ok"] = ok
        RESULT.parent.mkdir(parents=True, exist_ok=True)
        RESULT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            "drill_restore "
            f"ok={str(ok).lower()} head={report['migration_head']} "
            f"downgrade={report['migration_downgrade']} "
            f"uploads={str(report['upload_sha256_match']).lower()}"
        )
        return 0 if ok else 2
    except RuntimeError as exc:
        print(f"drill_failed {redact(str(exc), password)}")
        return 2
    finally:
        cleanup(password)


if __name__ == "__main__":
    raise SystemExit(main())
