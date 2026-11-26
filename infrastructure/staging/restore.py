"""Restore a staging backup into an isolated Compose project.

Refuses the development project and the live atlas-staging project. Postgres is
restored with pg_restore. Upload, model, and n8n files are extracted into fresh
volumes. The caller starts the application after this command exits.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from backup import CIPHER_PROGRAM, ROOT, BackupFailed, cipher_file, read_env_file
from backup_contract import (
    BackupContractError,
    assert_project,
    read_manifest,
    redact,
    restore_command,
    sha256_file,
    verify_tree,
)
from backup_secrets import SecretStoreError
from backup_secrets import resolve as resolve_passphrase

COMPOSE_FILE = ROOT / "infrastructure" / "compose.staging.yaml"


class RestoreFailed(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class DockerRestore:
    def __init__(
        self,
        project: str,
        env_file: Path,
        env: dict[str, str],
        compose_file: Path | None = None,
        postgres_user_key: str = "STAGING_POSTGRES_USER",
    ) -> None:
        self.project = project
        self.env_file = env_file
        self.env = env
        self.compose_file = compose_file or COMPOSE_FILE
        self.user = env.get(postgres_user_key, "atlas")

    def compose(
        self, args: list[str], stdin: bytes | None = None
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
            str(self.compose_file),
            *args,
        ]
        result = subprocess.run(
            command,
            cwd=ROOT,
            input=stdin,
            capture_output=True,
            check=False,
        )
        stdout = result.stdout.decode("utf-8", "replace")
        stderr = result.stderr.decode("utf-8", "replace")
        return subprocess.CompletedProcess(
            command,
            result.returncode,
            redact(stdout, self.env),
            redact(stderr, self.env),
        )

    def ensure_postgres(self) -> None:
        created = self.compose(["up", "-d", "postgres"])
        if created.returncode != 0:
            raise RestoreFailed(self._reason("postgres_start_failed", created))
        deadline = time.monotonic() + 60
        ready = created
        while time.monotonic() < deadline:
            ready = self.compose(
                [
                    "exec",
                    "-T",
                    "postgres",
                    "pg_isready",
                    "-U",
                    self.user,
                    "-d",
                    "postgres",
                ]
            )
            if ready.returncode == 0:
                return
            time.sleep(2)
        raise RestoreFailed(self._reason("postgres_not_ready", ready))

    def stop_writers(self) -> None:
        self.compose(["stop", "api", "web", "caddy", "n8n", "embedding-model"])

    def prepare_volumes(self) -> None:
        # Only create the writers whose volumes are restored. Without --no-deps,
        # Compose also creates embedding-model and requires its disposable image.
        created = self.compose(["up", "--no-start", "--no-deps", "api", "n8n"])
        if created.returncode != 0:
            raise RestoreFailed(self._reason("volume_create_failed", created))

    def public_tables(self, database: str) -> int:
        result = self.compose(
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                self.user,
                "-d",
                database,
                "-At",
                "-c",
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'",
            ]
        )
        if result.returncode != 0:
            raise RestoreFailed(self._reason("postgres_inspect_failed", result))
        try:
            return int(result.stdout.strip() or "0")
        except ValueError as exc:
            raise RestoreFailed("restore_failed postgres_inspect_failed") from exc

    def ensure_database(self, database: str) -> None:
        exists = self.compose(
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
                f"SELECT 1 FROM pg_database WHERE datname = '{database}'",
            ]
        )
        if exists.returncode != 0:
            raise RestoreFailed(self._reason("postgres_inspect_failed", exists))
        if exists.stdout.strip() == "1":
            return
        created = self.compose(
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                self.user,
                "-d",
                "postgres",
                "-c",
                f"CREATE DATABASE {database}",
            ]
        )
        if created.returncode != 0:
            raise RestoreFailed(self._reason("postgres_create_failed", created))

    def restore_dump(self, database: str, payload: bytes) -> None:
        self.ensure_database(database)
        clean = self.public_tables(database) > 0
        result = self.compose(
            ["exec", "-T", "postgres", *restore_command(self.user, database, clean=clean)],
            stdin=payload,
        )
        if result.returncode != 0:
            raise RestoreFailed(self._reason("postgres_restore_failed", result))

    def restore_globals(self, payload: bytes) -> None:
        result = self.compose(
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                self.user,
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=0",
            ],
            stdin=payload,
        )
        if result.returncode != 0:
            raise RestoreFailed(self._reason("globals_restore_failed", result))

    def extract_tree(self, service: str, container_path: str, payload: bytes, owner: str) -> None:
        cleared = self.compose(
            [
                "run",
                "-T",
                "--rm",
                "--no-deps",
                "--user",
                "root",
                "--entrypoint",
                "sh",
                service,
                "-c",
                f"find {container_path} -mindepth 1 -delete",
            ]
        )
        if cleared.returncode != 0:
            raise RestoreFailed(self._reason(f"{service}_clear_failed", cleared))
        extracted = self.compose(
            [
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
                "-xf",
                "-",
            ],
            stdin=payload,
        )
        if extracted.returncode != 0:
            raise RestoreFailed(self._reason(f"{service}_extract_failed", extracted))
        owned = self.compose(
            [
                "run",
                "-T",
                "--rm",
                "--no-deps",
                "--user",
                "root",
                "--entrypoint",
                "chown",
                service,
                "-R",
                owner,
                container_path,
            ]
        )
        if owned.returncode != 0:
            raise RestoreFailed(self._reason(f"{service}_chown_failed", owned))

    def _reason(self, reason: str, result: subprocess.CompletedProcess[str]) -> str:
        return f"restore_failed {reason} {result.stderr[:180]}".strip()


def decrypt(
    project: str,
    env_file: Path,
    source: Path,
    dest: Path,
    passphrase: str,
    env: dict[str, str],
    compose_file: Path | None = None,
) -> None:
    try:
        cipher_file(
            project,
            env_file,
            "dec",
            source,
            dest,
            passphrase,
            env,
            compose_file=compose_file,
        )
    except BackupFailed as exc:
        raise RestoreFailed(exc.reason) from exc


def decrypt_local(source: Path, dest: Path, passphrase: str) -> None:
    """Decrypt without Compose for read-only archive verification."""
    result = subprocess.run(
        [sys.executable, "-c", CIPHER_PROGRAM, "dec"],
        input=source.read_bytes(),
        capture_output=True,
        env={**os.environ, "ATLAS_BACKUP_PASSPHRASE": passphrase},
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        raise RestoreFailed("restore_failed decrypt_failed")
    dest.write_bytes(result.stdout)


def open_validated_archive(path: Path) -> tarfile.TarFile:
    size = path.stat().st_size
    gzip_header = path.read_bytes()[:2] == b"\x1f\x8b"
    print(f"archive_check bytes={size} gzip_header={str(gzip_header).lower()}", file=sys.stderr)
    if not gzip_header:
        raise RestoreFailed("restore_failed gzip_header")
    try:
        return tarfile.open(path, "r:gz")
    except (OSError, tarfile.TarError) as exc:
        raise RestoreFailed("restore_failed archive_read") from exc


def verify_archive(*, archive: Path, passphrase: str) -> str:
    """Validate an archive without Docker, Compose, or persistent resources."""
    if archive.name.endswith(".tar.gz.enc") and not passphrase:
        raise BackupContractError("backup_refused passphrase_required")
    with tempfile.TemporaryDirectory(prefix="atlas-verify-") as temporary:
        root = Path(temporary)
        tar_path = root / "archive.tar.gz"
        if archive.name.endswith(".tar.gz.enc"):
            decrypt_local(archive, tar_path, passphrase)
        else:
            tar_path = archive
        if tar_path.stat().st_size < 2 or tar_path.read_bytes()[:2] != b"\x1f\x8b":
            raise RestoreFailed("restore_failed gzip_header")
        extract_root = root / "tree"
        extract_root.mkdir()
        with open_validated_archive(tar_path) as packed:
            packed.extractall(extract_root, filter="data")
            member_count = len(packed.getmembers())
        try:
            manifest = read_manifest(extract_root / "manifest.json")
            verify_tree(extract_root, manifest)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RestoreFailed("restore_failed manifest") from exc
        decrypted_bytes = tar_path.stat().st_size
    return f"verify_ok archive={archive.name} members={member_count} bytes={decrypted_bytes}"


def compare_upload_trees(expected: Path, actual: dict[str, str]) -> str:
    expected_files = {
        path.relative_to(expected).as_posix(): sha256_file(path)
        for path in expected.rglob("*")
        if path.is_file()
    }
    missing = sum(name not in actual for name in expected_files)
    mismatched = sum(
        name in actual and actual[name] != digest
        for name, digest in expected_files.items()
    )
    unexpected = sum(name not in expected_files for name in actual)
    matched = len(expected_files) - missing - mismatched
    return (
        f"upload_check matched={matched} missing={missing} "
        f"unexpected={unexpected} mismatched={mismatched}"
    )


def verify_restored_uploads(
    *,
    project: str,
    env_file: Path,
    archive: Path,
    passphrase: str,
    compose_file: Path | None = None,
    postgres_user_key: str = "STAGING_POSTGRES_USER",
) -> str:
    """Compare restored storage with the uploaded-files archive, read-only."""
    assert_project(project, restore=True)
    env = read_env_file(env_file)
    docker = DockerRestore(
        project,
        env_file,
        env,
        compose_file=compose_file,
        postgres_user_key=postgres_user_key,
    )
    with tempfile.TemporaryDirectory(prefix="atlas-upload-verify-") as temporary:
        root = Path(temporary)
        tar_path = root / "archive.tar.gz"
        decrypt_local(archive, tar_path, passphrase)
        tree = root / "tree"
        tree.mkdir()
        with open_validated_archive(tar_path) as packed:
            packed.extractall(tree, filter="data")
        manifest = read_manifest(tree / "manifest.json")
        verify_tree(tree, manifest)
        uploads = tree / "uploads.tar"
        expected = root / "expected"
        expected.mkdir()
        with tarfile.open(uploads, "r:") as packed:
            packed.extractall(expected, filter="data")
        result = docker.compose(
            [
                "exec",
                "-T",
                "api",
                "python",
                "-c",
                (
                    "import hashlib,json,pathlib; "
                "root=pathlib.Path('/var/lib/atlas/storage'); "
                "actual={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() "
                "for p in root.rglob('*') if p.is_file()}; "
                    "print(json.dumps(actual))"
                ),
            ],
            stdin=None,
        )
        if result.returncode != 0:
            raise RestoreFailed("restore_failed uploads_inspect")
        try:
            actual = json.loads(result.stdout.strip() or "{}")
        except ValueError as exc:
            raise RestoreFailed("restore_failed uploads_inspect") from exc
        if not isinstance(actual, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in actual.items()
        ):
            raise RestoreFailed("restore_failed uploads_inspect")
        summary = compare_upload_trees(expected, actual)
        if any(f"{field}=0" not in summary for field in ("missing", "unexpected", "mismatched")):
            raise RestoreFailed(f"restore_failed {summary}")
    return summary


def database_name(record_file: str) -> str:
    prefix = "postgres-"
    suffix = ".dump"
    if not record_file.startswith(prefix) or not record_file.endswith(suffix):
        raise RestoreFailed("restore_failed postgres_name")
    name = record_file[len(prefix) : -len(suffix)]
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
        raise RestoreFailed("restore_failed postgres_name")
    return name


def restore_backup(
    *,
    project: str,
    env_file: Path,
    archive: Path,
    passphrase: str,
    compose_file: Path | None = None,
    postgres_user_key: str = "STAGING_POSTGRES_USER",
) -> str:
    assert_project(project, restore=True)
    env = read_env_file(env_file)
    if archive.suffix == ".enc" and not passphrase:
        raise BackupContractError("backup_refused passphrase_required")
    docker = DockerRestore(
        project,
        env_file,
        env,
        compose_file=compose_file,
        postgres_user_key=postgres_user_key,
    )
    with tempfile.TemporaryDirectory(prefix="atlas-restore-") as temporary:
        root = Path(temporary)
        tar_path = archive
        if archive.name.endswith(".tar.gz.enc"):
            tar_path = root / "archive.tar.gz"
            decrypt_local(archive, tar_path, passphrase)
        extract_root = root / "tree"
        extract_root.mkdir()
        with open_validated_archive(tar_path) as packed:
            packed.extractall(extract_root, filter="data")
        manifest = read_manifest(extract_root / "manifest.json")
        verify_tree(extract_root, manifest)
        docker.stop_writers()
        docker.ensure_postgres()
        docker.prepare_volumes()
        docker.restore_globals((extract_root / "globals.sql").read_bytes())
        postgres = manifest["postgres"]
        if not isinstance(postgres, list):
            raise RestoreFailed("restore_failed manifest")
        for record in postgres:
            if not isinstance(record, dict):
                raise RestoreFailed("restore_failed manifest")
            name = database_name(str(record["file"]))
            docker.restore_dump(name, (extract_root / str(record["file"])).read_bytes())
        docker.extract_tree(
            "api",
            "/var/lib/atlas/storage",
            (extract_root / "uploads.tar").read_bytes(),
            "10001:10001",
        )
        docker.extract_tree(
            "api",
            "/var/lib/atlas/models",
            (extract_root / "models.tar").read_bytes(),
            "10001:10001",
        )
        docker.extract_tree(
            "n8n", "/home/node/.n8n", (extract_root / "n8n.tar").read_bytes(), "1000:1000"
        )
    return f"restore_ok archive={archive.name}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore a staging backup into an isolated project"
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--verify-uploads", action="store_true")
    args = parser.parse_args()
    try:
        passphrase = resolve_passphrase()
        if args.verify_only and args.verify_uploads:
            raise BackupContractError("backup_refused verification_mode")
        if args.verify_only:
            line = verify_archive(archive=args.archive, passphrase=passphrase)
        elif args.verify_uploads:
            line = verify_restored_uploads(
                project=args.project,
                env_file=args.env_file,
                archive=args.archive,
                passphrase=passphrase,
            )
        else:
            line = restore_backup(
                project=args.project,
                env_file=args.env_file,
                archive=args.archive,
                passphrase=passphrase,
            )
    except BackupContractError as exc:
        print(exc.reason, file=sys.stderr)
        return 2
    except RestoreFailed as exc:
        print(exc.reason, file=sys.stderr)
        return 2
    except (OSError, tarfile.TarError, SecretStoreError) as exc:
        print(f"restore_failed {exc.__class__.__name__}", file=sys.stderr)
        return 1
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
