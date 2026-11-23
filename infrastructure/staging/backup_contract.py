"""Rules for staging backups. This module does not connect to Docker or the database."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

ARCHIVE_RE = re.compile(r"^atlas-\d{8}T\d{6}Z(?:\.tar\.gz|\.tar\.gz\.enc)$")
PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
BACKUP_PROJECTS_REFUSED = frozenset({"atlas", "infrastructure", "titan", "legalstats"})
RESTORE_PROJECTS_REFUSED = BACKUP_PROJECTS_REFUSED | {"atlas-staging"}
REQUIRED_FILES = (
    "globals.sql",
    "uploads.tar",
    "models.tar",
    "n8n.tar",
)
EXCLUDED = (
    "ollama model weights; pull nomic-embed-text:v1.5 again",
    "mailpit mailbox",
    "caddy certificates",
)
KEYS_NOT_IN_ARCHIVE = (
    "STAGING_SECRET_KEY",
    "STAGING_POSTGRES_PASSWORD",
    "STAGING_N8N_ENCRYPTION_KEY",
    "ATLAS_BACKUP_PASSPHRASE",
    "AWS_SECRET_ACCESS_KEY",
)
_SENSITIVE = ("PASSWORD", "SECRET", "PASSPHRASE", "TOKEN")


class BackupContractError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def archive_stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("atlas-%Y%m%dT%H%M%SZ")


def assert_project(name: str, *, restore: bool) -> None:
    if not PROJECT_RE.fullmatch(name):
        raise BackupContractError("backup_refused project_name")
    refused = RESTORE_PROJECTS_REFUSED if restore else BACKUP_PROJECTS_REFUSED
    if name in refused:
        raise BackupContractError(f"backup_refused protected_project={name}")


def expired_archives(names: list[str], keep: int) -> list[str]:
    if keep < 1:
        raise BackupContractError("backup_refused retention")
    valid = sorted(name for name in names if ARCHIVE_RE.fullmatch(name))
    if len(valid) <= keep:
        return []
    return valid[: len(valid) - keep]


def offhost_decision(uri: str, passphrase: str, access_key: str, secret_key: str) -> str:
    if not uri.strip():
        return "skipped"
    if not passphrase:
        raise BackupContractError("backup_refused offhost_requires_encryption")
    if not uri.startswith("s3://") or uri.count("/") < 3:
        raise BackupContractError("backup_refused offhost_uri")
    if not access_key or not secret_key:
        raise BackupContractError("backup_refused offhost_credentials_missing")
    return "upload"


def dump_command(user: str, database: str) -> list[str]:
    return ["pg_dump", "-U", user, "-d", database, "-Fc", "--no-password"]


def globals_command(user: str) -> list[str]:
    return ["pg_dumpall", "-U", user, "--globals-only", "--no-password", "--no-role-passwords"]


def restore_command(user: str, database: str, *, clean: bool) -> list[str]:
    command = [
        "pg_restore",
        "-U",
        user,
        "-d",
        database,
        "--no-owner",
        "--no-acl",
        "--no-password",
        "--exit-on-error",
    ]
    if clean:
        command[5:5] = ["--clean", "--if-exists"]
    return command


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, object]:
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def build_manifest(
    *,
    created_at: str,
    project: str,
    records: dict[str, dict[str, object]],
) -> dict[str, object]:
    for name in REQUIRED_FILES:
        if name not in records:
            raise BackupContractError(f"backup_refused missing={name}")
    postgres = [record for key, record in sorted(records.items()) if key.startswith("postgres-")]
    if not postgres:
        raise BackupContractError("backup_refused missing=postgres")
    return {
        "format": 1,
        "created_at": created_at,
        "project": project,
        "postgres": postgres,
        "globals": records["globals.sql"],
        "uploads": records["uploads.tar"],
        "models": records["models.tar"],
        "n8n": records["n8n.tar"],
        "excluded": list(EXCLUDED),
        "keys_not_in_archive": list(KEYS_NOT_IN_ARCHIVE),
    }


def manifest_records(manifest: dict[str, object]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    postgres = manifest.get("postgres")
    if not isinstance(postgres, list) or not postgres:
        raise BackupContractError("backup_refused manifest")
    records.extend(_record(item) for item in postgres)
    for key in ("globals", "uploads", "models", "n8n"):
        records.append(_record(manifest.get(key)))
    return records


def verify_tree(root: Path, manifest: dict[str, object]) -> None:
    for record in manifest_records(manifest):
        name = str(record["file"])
        path = root / name
        if not path.is_file():
            raise BackupContractError(f"backup_refused missing={name}")
        if path.stat().st_size != record["bytes"]:
            raise BackupContractError(f"backup_refused size={name}")
        if sha256_file(path) != record["sha256"]:
            raise BackupContractError(f"backup_refused sha256={name}")


def acquire_lock(path: Path, now: float, stale_after_seconds: float = 6 * 60 * 60) -> None:
    if path.exists():
        age = now - path.stat().st_mtime
        if age < stale_after_seconds:
            raise BackupContractError("backup_refused backup_busy")
        path.unlink()
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise BackupContractError("backup_refused backup_busy") from exc
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)


def redact(text: str, env: dict[str, str]) -> str:
    redacted = text
    for key, value in env.items():
        if len(value) < 8:
            continue
        if any(part in key for part in _SENSITIVE) or key.endswith("_KEY"):
            redacted = redacted.replace(value, "[redacted]")
    return redacted


def _record(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise BackupContractError("backup_refused manifest")
    file_name = value.get("file")
    size = value.get("bytes")
    digest = value.get("sha256")
    if not isinstance(file_name, str) or not isinstance(size, int) or not isinstance(digest, str):
        raise BackupContractError("backup_refused manifest")
    if Path(file_name).name != file_name:
        raise BackupContractError("backup_refused manifest")
    return value


def dump_uses_logical_backup(command: list[str]) -> bool:
    text = " ".join(command)
    return (
        "pg_dump" in command
        and "-Fc" in command
        and "volume" not in text
        and "/var/lib/postgresql" not in text
    )


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_manifest(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BackupContractError("backup_refused manifest")
    return payload
