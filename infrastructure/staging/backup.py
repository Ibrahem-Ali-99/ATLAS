"""Create a staging backup.

Postgres is dumped with pg_dump while the server is running. The upload, model,
and n8n directories are archived after n8n is stopped so its SQLite file is
quiet. Ollama weights are left out; the provision command can pull them again.
The archive does not contain the Compose env file. A passphrase encrypts the
archive, and an S3 upload is refused when that passphrase is missing.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path

from backup_contract import (
    BackupContractError,
    acquire_lock,
    archive_stamp,
    assert_project,
    build_manifest,
    dump_command,
    expired_archives,
    file_record,
    globals_command,
    offhost_decision,
    redact,
    write_manifest,
)
from backup_secrets import SecretStoreError
from backup_secrets import initialize as initialize_passphrase
from backup_secrets import resolve as resolve_passphrase

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "infrastructure" / "compose.staging.yaml"
DEFAULT_ENV = ROOT / "infrastructure" / "staging" / ".env"
DEFAULT_DIR = ROOT / "infrastructure" / "staging" / "backups"
AWS_IMAGE = "amazon/aws-cli:2.22.35"
CIPHER_PROGRAM = """
import os
import sys

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

def derive(salt: bytes) -> bytes:
    return PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=200_000,
    ).derive(os.environ["ATLAS_BACKUP_PASSPHRASE"].encode())

raw = sys.stdin.buffer.read()
if sys.argv[1] == "enc":
    salt = os.urandom(16)
    nonce = os.urandom(12)
    sealed = AESGCM(derive(salt)).encrypt(nonce, raw, None)
    sys.stdout.buffer.write(b"ATLAS1" + salt + nonce + sealed)
elif raw.startswith(b"ATLAS1") and len(raw) > 34:
    salt, nonce, body = raw[6:22], raw[22:34], raw[34:]
    sys.stdout.buffer.write(AESGCM(derive(salt)).decrypt(nonce, body, None))
else:
    sys.exit(2)
"""


class BackupFailed(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def cipher_file(
    project: str,
    env_file: Path,
    mode: str,
    source: Path,
    dest: Path,
    passphrase: str,
    env: dict[str, str],
) -> None:
    command = [
        "docker",
        "compose",
        "--project-name",
        project,
        "--project-directory",
        str(ROOT / "infrastructure"),
        "--env-file",
        str(env_file),
        "-f",
        str(COMPOSE_FILE),
        "run",
        "-T",
        "--rm",
        "--no-deps",
        "--user",
        "10001",
        "--entrypoint",
        "python",
        "-e",
        "ATLAS_BACKUP_PASSPHRASE",
        "api",
        "-c",
        CIPHER_PROGRAM,
        mode,
    ]
    with source.open("rb") as stdin, dest.open("wb") as stdout:
        result = subprocess.run(
            command,
            stdin=stdin,
            stdout=stdout,
            stderr=subprocess.PIPE,
            env={**os.environ, "ATLAS_BACKUP_PASSPHRASE": passphrase},
            check=False,
        )
    detail = redact(result.stderr.decode("utf-8", "replace"), env)
    if result.returncode != 0 or dest.stat().st_size == 0:
        dest.unlink(missing_ok=True)
        label = "encrypt_failed" if mode == "enc" else "decrypt_failed"
        prefix = "backup_failed" if mode == "enc" else "restore_failed"
        raise BackupFailed(f"{prefix} {label} {detail[:180]}".strip())


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


class DockerBackup:
    def __init__(self, project: str, env_file: Path, env: dict[str, str]) -> None:
        self.project = project
        self.env_file = env_file
        self.env = env
        self.user = env.get("STAGING_POSTGRES_USER", "atlas")

    def databases(self) -> list[str]:
        result = self._compose(
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                self.user,
                "-d",
                "postgres",
                "-At",
                "-c",
                "SELECT datname FROM pg_database "
                "WHERE datistemplate = false AND datname <> 'postgres' ORDER BY 1",
            ]
        )
        if result.returncode != 0:
            raise BackupFailed(self._reason("postgres_list_failed", result))
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not names:
            raise BackupFailed("backup_failed postgres_list_failed")
        return names

    def dump(self, database: str, path: Path) -> None:
        self._stream(
            ["exec", "-T", "postgres", *dump_command(self.user, database)],
            path,
            "postgres_dump_failed",
        )

    def dump_globals(self, path: Path) -> None:
        self._stream(
            ["exec", "-T", "postgres", *globals_command(self.user)],
            path,
            "globals_dump_failed",
        )

    def stop(self, service: str) -> None:
        result = self._compose(["stop", service])
        if result.returncode != 0:
            raise BackupFailed(self._reason(f"{service}_stop_failed", result))

    def start(self, service: str) -> None:
        result = self._compose(["start", service])
        if result.returncode != 0:
            raise BackupFailed(self._reason(f"{service}_start_failed", result))

    def archive_tree(self, service: str, container_path: str, path: Path) -> None:
        if service == "n8n":
            args = [
                "run",
                "-T",
                "--rm",
                "--no-deps",
                "--user",
                "root",
                "--entrypoint",
                "tar",
                service,
                "-C",
                container_path,
                "-cf",
                "-",
                ".",
            ]
        else:
            args = [
                "exec",
                "-T",
                "--user",
                "root",
                service,
                "tar",
                "-C",
                container_path,
                "-cf",
                "-",
                ".",
            ]
        self._stream(args, path, f"{service}_archive_failed")

    def encrypt(self, source: Path, dest: Path, passphrase: str) -> None:
        cipher_file(self.project, self.env_file, "enc", source, dest, passphrase, self.env)

    def upload(self, archive: Path, uri: str, endpoint: str) -> None:
        key = uri[len("s3://") :]
        bucket, _, prefix = key.partition("/")
        destination = f"s3://{bucket}/{prefix.rstrip('/')}/{archive.name}"
        command = [
            "docker",
            "run",
            "--rm",
            "-e",
            "AWS_ACCESS_KEY_ID",
            "-e",
            "AWS_SECRET_ACCESS_KEY",
            "-e",
            "AWS_DEFAULT_REGION",
            "-v",
            f"{archive.parent}:/backup:ro",
            AWS_IMAGE,
            "s3",
            "cp",
            f"/backup/{archive.name}",
            destination,
            "--only-show-errors",
        ]
        if endpoint:
            command.extend(["--endpoint-url", endpoint])
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "AWS_ACCESS_KEY_ID": os.environ.get("AWS_ACCESS_KEY_ID", ""),
                "AWS_SECRET_ACCESS_KEY": os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
                "AWS_DEFAULT_REGION": os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            },
            check=False,
        )
        if result.returncode != 0:
            detail = redact(f"{result.stdout}\n{result.stderr}", self.env)
            raise BackupFailed(f"backup_failed offhost_upload_failed {detail[:180]}".strip())

    def _stream(self, args: list[str], path: Path, reason: str) -> None:
        with path.open("wb") as handle:
            result = self._compose(args, stdout=handle, text=False)
        if result.returncode != 0 or path.stat().st_size == 0:
            path.unlink(missing_ok=True)
            raise BackupFailed(self._reason(reason, result))

    def _compose(
        self,
        args: list[str],
        stdout: int | None = subprocess.PIPE,
        text: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            "docker",
            "compose",
            "--project-name",
            self.project,
            "--project-directory",
            str(ROOT / "infrastructure"),
            "--env-file",
            str(self.env_file),
            "-f",
            str(COMPOSE_FILE),
            *args,
        ]
        result = subprocess.run(
            command, cwd=ROOT, stdout=stdout, stderr=subprocess.PIPE, text=text, check=False
        )
        if isinstance(result.stderr, bytes):
            result.stderr = result.stderr.decode("utf-8", "replace")
        if isinstance(result.stderr, str):
            result.stderr = redact(result.stderr, self.env)
        if isinstance(result.stdout, str):
            result.stdout = redact(result.stdout, self.env)
        return result

    def _reason(self, reason: str, result: subprocess.CompletedProcess[str]) -> str:
        detail = result.stderr if isinstance(result.stderr, str) else ""
        return f"backup_failed {reason} {detail[:180]}".strip()


def pack(work: Path, destination: Path) -> None:
    with tarfile.open(destination, "w:gz") as archive:
        for path in sorted(work.iterdir()):
            archive.add(path, arcname=path.name)


def create_backup(
    *,
    project: str,
    env_file: Path,
    backup_dir: Path,
    keep: int,
    passphrase: str,
    s3_uri: str,
    s3_endpoint: str,
    access_key: str,
    secret_key: str,
    now: datetime | None = None,
) -> str:
    assert_project(project, restore=False)
    decision = offhost_decision(s3_uri, passphrase, access_key, secret_key)
    env = read_env_file(env_file)
    backup_dir.mkdir(parents=True, exist_ok=True)
    moment = now or datetime.now(UTC)
    stamp = archive_stamp(moment)
    lock = backup_dir / ".lock"
    acquire_lock(lock, moment.timestamp())
    work = backup_dir / f"{stamp}.partial"
    plain = backup_dir / f"{stamp}.tar.gz"
    encrypted = backup_dir / f"{stamp}.tar.gz.enc"
    docker = DockerBackup(project, env_file, env)
    n8n_stopped = False
    try:
        work.mkdir()
        records: dict[str, dict[str, object]] = {}
        for database in docker.databases():
            dump_path = work / f"postgres-{database}.dump"
            docker.dump(database, dump_path)
            records[dump_path.name] = file_record(dump_path)
        globals_path = work / "globals.sql"
        docker.dump_globals(globals_path)
        records[globals_path.name] = file_record(globals_path)
        docker.stop("n8n")
        n8n_stopped = True
        for service, container_path, name in (
            ("api", "/var/lib/atlas/storage", "uploads.tar"),
            ("api", "/var/lib/atlas/models", "models.tar"),
            ("n8n", "/home/node/.n8n", "n8n.tar"),
        ):
            target = work / name
            docker.archive_tree(service, container_path, target)
            records[name] = file_record(target)
        docker.start("n8n")
        n8n_stopped = False
        manifest = build_manifest(
            created_at=moment.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            project=project,
            records=records,
        )
        write_manifest(work / "manifest.json", manifest)
        pack(work, plain)
        archive = plain
        encrypted_flag = "false"
        if passphrase:
            docker.encrypt(plain, encrypted, passphrase)
            plain.unlink()
            archive = encrypted
            encrypted_flag = "true"
        deleted = expired_archives(
            [path.name for path in backup_dir.iterdir() if path.is_file()],
            keep,
        )
        for name in deleted:
            (backup_dir / name).unlink()
        if decision == "upload":
            docker.upload(archive, s3_uri, s3_endpoint)
        free = shutil.disk_usage(backup_dir).free
        return (
            f"backup_ok archive={archive.name} bytes={archive.stat().st_size} "
            f"disk_free={free} deleted={len(deleted)} offhost={decision} encrypted={encrypted_flag}"
        )
    except (BackupFailed, BackupContractError):
        if n8n_stopped:
            try:
                docker.start("n8n")
            except BackupFailed:
                pass
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
        lock.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up the staging stack")
    parser.add_argument(
        "--project", default=os.environ.get("ATLAS_BACKUP_PROJECT", "atlas-staging")
    )
    parser.add_argument(
        "--env-file", type=Path, default=Path(os.environ.get("ATLAS_COMPOSE_ENV", DEFAULT_ENV))
    )
    parser.add_argument(
        "--backup-dir", type=Path, default=Path(os.environ.get("ATLAS_BACKUP_DIR", DEFAULT_DIR))
    )
    parser.add_argument("--keep", type=int, default=int(os.environ.get("ATLAS_BACKUP_KEEP", "14")))
    parser.add_argument("--init-passphrase", action="store_true")
    args = parser.parse_args()
    try:
        if args.init_passphrase:
            path = initialize_passphrase()
            print(f"passphrase_store_initialized path={path}")
            return 0
        line = create_backup(
            project=args.project,
            env_file=args.env_file,
            backup_dir=args.backup_dir,
            keep=args.keep,
            passphrase=resolve_passphrase(),
            s3_uri=os.environ.get("ATLAS_BACKUP_S3_URI", ""),
            s3_endpoint=os.environ.get("ATLAS_BACKUP_S3_ENDPOINT", ""),
            access_key=os.environ.get("AWS_ACCESS_KEY_ID", ""),
            secret_key=os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
        )
    except BackupContractError as exc:
        print(exc.reason, file=sys.stderr)
        return 2
    except BackupFailed as exc:
        print(exc.reason, file=sys.stderr)
        return 2
    except (OSError, SecretStoreError) as exc:
        print(f"backup_failed {exc.__class__.__name__}", file=sys.stderr)
        return 1
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
