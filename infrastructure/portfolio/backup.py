"""Backup and restore the portfolio database only.

The archive contains password hashes for the fictional demo accounts. Keep it
on the host. It does not contain the env file or a provider key.
"""

from __future__ import annotations

import argparse
import subprocess
import tarfile
from pathlib import Path

from project import LIVE_PROJECT, BackupFailed, ProjectRefused, assert_project, compose_command

ARCHIVE_MEMBERS = ("postgres.dump", "portfolio-docs.tar")

def docker_mount(path: Path) -> str:
    resolved = path.resolve().as_posix()
    if len(resolved) >= 2 and resolved[1] == ":":
        return f"/{resolved[0].lower()}{resolved[2:]}"
    return resolved


def volume_name(project: str, logical: str) -> str:
    assert_project(project)
    result = subprocess.run(
        [
            "docker",
            "volume",
            "ls",
            "-q",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--filter",
            f"label=com.docker.compose.volume={logical}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    found = [line for line in result.stdout.splitlines() if line.strip()]
    if result.returncode != 0 or len(found) != 1 or not found[0].startswith(project):
        raise BackupFailed(logical)
    return found[0]


def postgres_container(project: str) -> str:
    assert_project(project)
    name = f"{project}-postgres-1"
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.Name}}", name],
        check=False,
        capture_output=True,
        text=True,
    )
    inspected = result.stdout.strip().lstrip("/")
    if result.returncode != 0 or inspected != name:
        raise BackupFailed("postgres")
    return name


def create_backup(project: str, destination: Path) -> Path:
    assert_project(project)
    destination.parent.mkdir(parents=True, exist_ok=True)
    work = destination.parent / f".{destination.stem}-work"
    if work.exists():
        raise BackupFailed("workspace")
    work.mkdir()
    try:
        database = postgres_container(project)
        dumped = subprocess.run(
            [
                "docker",
                "exec",
                database,
                "pg_dump",
                "-U",
                "atlas",
                "-d",
                "atlas_portfolio",
                "-Fc",
                "--no-owner",
                "--no-acl",
                "-f",
                "/tmp/portfolio.dump",
            ],
            check=False,
        )
        if dumped.returncode != 0:
            raise BackupFailed("dump")
        copied = subprocess.run(
            ["docker", "cp", f"{database}:/tmp/portfolio.dump", str(work / "postgres.dump")],
            check=False,
        )
        subprocess.run(["docker", "exec", database, "rm", "-f", "/tmp/portfolio.dump"], check=False)
        if copied.returncode != 0:
            raise BackupFailed("copy")
        docs = volume_name(project, "portfolio_docs")
        packed = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{docs}:/data:ro",
                "-v",
                f"{docker_mount(work)}:/out",
                "pgvector/pgvector:pg17",
                "tar",
                "-C",
                "/data",
                "-cf",
                "/out/portfolio-docs.tar",
                ".",
            ],
            check=False,
        )
        if packed.returncode != 0:
            raise BackupFailed("documents")
        with tarfile.open(destination, "w:gz") as archive:
            for name in ARCHIVE_MEMBERS:
                archive.add(work / name, arcname=name)
    finally:
        for child in work.glob("*"):
            child.unlink(missing_ok=True)
        work.rmdir()
    return destination


def restore_archive(project: str, env_file: Path, archive: Path) -> None:
    assert_project(project)
    if not archive.is_file():
        raise BackupFailed("archive")
    work = archive.parent / f".{archive.stem}-restore"
    if work.exists():
        raise BackupFailed("workspace")
    work.mkdir()
    try:
        with tarfile.open(archive, "r:gz") as packed:
            members = packed.getmembers()
            if [member.name for member in members] != list(ARCHIVE_MEMBERS):
                raise BackupFailed("archive")
            packed.extractall(work, filter="data")
        database = postgres_container(project)
        compose = compose_command(project, env_file)
        stopped = subprocess.run([*compose, "stop", "api", "web"], check=False)
        if stopped.returncode != 0:
            raise BackupFailed("stop")
        copied = subprocess.run(
            ["docker", "cp", str(work / "postgres.dump"), f"{database}:/tmp/portfolio.dump"],
            check=False,
        )
        if copied.returncode != 0:
            raise BackupFailed("copy")
        replaced = subprocess.run(
            [
                "docker",
                "exec",
                database,
                "psql",
                "-U",
                "atlas",
                "-d",
                "atlas_portfolio",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = 'atlas_portfolio' AND pid <> pg_backend_pid(); "
                "DROP SCHEMA IF EXISTS public CASCADE; "
                "CREATE SCHEMA public;",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        restored = subprocess.run(
            [
                "docker",
                "exec",
                database,
                "pg_restore",
                "-U",
                "atlas",
                "-d",
                "atlas_portfolio",
                "--no-owner",
                "--no-acl",
                "/tmp/portfolio.dump",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        subprocess.run(["docker", "exec", database, "rm", "-f", "/tmp/portfolio.dump"], check=False)
        errors = [
            line
            for line in restored.stderr.splitlines()
            if "ERROR:" in line and "already exists" not in line
        ]
        if replaced.returncode != 0 or errors:
            detail = " ".join(
                line
                for line in (replaced.stderr + restored.stderr).splitlines()
                if line.strip() and "://" not in line
            )[-240:]
            raise BackupFailed(detail or "restore")
        docs = volume_name(project, "portfolio_docs")
        unpacked = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{docs}:/data",
                "-v",
                f"{docker_mount(work)}:/out:ro",
                "pgvector/pgvector:pg17",
                "tar",
                "-C",
                "/data",
                "-xf",
                "/out/portfolio-docs.tar",
            ],
            check=False,
        )
        if unpacked.returncode != 0:
            raise BackupFailed("documents")
        started = subprocess.run([*compose, "start", "api", "web"], check=False)
        if started.returncode != 0:
            raise BackupFailed("start")
    finally:
        for child in work.glob("*"):
            child.unlink(missing_ok=True)
        work.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("backup", "restore"))
    parser.add_argument("--project", default=LIVE_PROJECT)
    parser.add_argument("--env-file", type=Path, default=Path("infrastructure/portfolio/.env"))
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == "backup":
            create_backup(args.project, args.archive)
            print(f"Portfolio backup written to {args.archive.name}")
        else:
            restore_archive(args.project, args.env_file, args.archive)
            print("Portfolio database restored. Other Compose projects were not changed.")
    except ProjectRefused:
        print("Portfolio backup refused. The target is not the isolated demo project.")
        return 2
    except BackupFailed:
        print("Portfolio backup did not finish. Other Compose projects were not changed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
