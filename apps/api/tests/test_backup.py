import json
import os
import sys
import time
from pathlib import Path

from tests.bootstrap import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "infrastructure" / "staging"))

import backup_contract  # noqa: E402


def test_daily_retention_keeps_the_newest_archives(tmp_path: Path) -> None:
    names = [f"atlas-202611{day:02d}T021500Z.tar.gz.enc" for day in range(1, 17)]
    expired = backup_contract.expired_archives(names, keep=14)
    assert expired == names[:2]
    assert backup_contract.expired_archives(names[:3], keep=14) == []
    assert "notes.txt" not in backup_contract.expired_archives(names[:2] + ["notes.txt"], keep=1)


def test_offhost_upload_requires_encryption_and_credentials() -> None:
    assert backup_contract.offhost_decision("", "", "", "") == "skipped"
    try:
        backup_contract.offhost_decision("s3://bucket/atlas", "", "key", "secret")
    except backup_contract.BackupContractError as exc:
        assert exc.reason == "backup_refused offhost_requires_encryption"
    else:
        raise AssertionError("plaintext upload was accepted")
    try:
        backup_contract.offhost_decision("s3://bucket/atlas", "passphrase", "", "")
    except backup_contract.BackupContractError as exc:
        assert exc.reason == "backup_refused offhost_credentials_missing"
    else:
        raise AssertionError("upload without credentials was accepted")
    assert (
        backup_contract.offhost_decision("s3://bucket/atlas", "passphrase", "key", "secret")
        == "upload"
    )


def test_restore_refuses_the_live_projects() -> None:
    for name in ("atlas", "atlas-staging", "infrastructure", "titan", "legalstats"):
        try:
            backup_contract.assert_project(name, restore=True)
        except backup_contract.BackupContractError as exc:
            assert "protected_project" in exc.reason
        else:
            raise AssertionError(f"{name} was accepted for restore")
    backup_contract.assert_project("atlas-staging", restore=False)
    backup_contract.assert_project("atlas-backup-proof", restore=True)


def test_dump_command_is_a_logical_backup() -> None:
    command = backup_contract.dump_command("atlas", "atlas")
    assert backup_contract.dump_uses_logical_backup(command)
    assert "--no-role-passwords" in backup_contract.globals_command("atlas")
    clean = backup_contract.restore_command("atlas", "atlas", clean=True)
    assert "--clean" in clean and "--if-exists" in clean
    assert "--clean" not in backup_contract.restore_command("atlas", "atlas", clean=False)
    volume_copy = ["docker", "volume", "cp", "/var/lib/postgresql/data"]
    assert backup_contract.dump_uses_logical_backup(volume_copy) is False


def test_manifest_detects_a_changed_file(tmp_path: Path) -> None:
    for name in ("globals.sql", "uploads.tar", "models.tar", "n8n.tar", "postgres-atlas.dump"):
        (tmp_path / name).write_bytes(name.encode())
    records = {
        name: backup_contract.file_record(tmp_path / name)
        for name in (
            "globals.sql",
            "uploads.tar",
            "models.tar",
            "n8n.tar",
            "postgres-atlas.dump",
        )
    }
    manifest = backup_contract.build_manifest(
        created_at="2026-11-23T02:15:00Z",
        project="atlas-backup-proof",
        records=records,
    )
    backup_contract.verify_tree(tmp_path, manifest)
    (tmp_path / "uploads.tar").write_bytes(b"uploads.xxx")
    try:
        backup_contract.verify_tree(tmp_path, manifest)
    except backup_contract.BackupContractError as exc:
        assert exc.reason == "backup_refused sha256=uploads.tar"
    else:
        raise AssertionError("changed archive was accepted")
    assert json.loads(json.dumps(manifest))["excluded"]


def test_a_second_run_waits_instead_of_overlapping(tmp_path: Path) -> None:
    lock = tmp_path / ".lock"
    now = time.time()
    backup_contract.acquire_lock(lock, now)
    try:
        backup_contract.acquire_lock(lock, now + 10)
    except backup_contract.BackupContractError as exc:
        assert exc.reason == "backup_refused backup_busy"
    else:
        raise AssertionError("overlapping backup was accepted")
    stale = now - 7 * 60 * 60
    os.utime(lock, (stale, stale))
    backup_contract.acquire_lock(lock, now)
    assert lock.read_text(encoding="utf-8")


def test_redaction_and_scheduler_files() -> None:
    hidden = backup_contract.redact(
        "passphrase=supersecretvalue", {"ATLAS_BACKUP_PASSPHRASE": "supersecretvalue"}
    )
    assert "supersecretvalue" not in hidden
    staging = REPO_ROOT / "infrastructure" / "staging"
    timer = (staging / "atlas-backup.timer").read_text(encoding="utf-8")
    service = (staging / "atlas-backup.service").read_text(encoding="utf-8")
    example = (staging / "backup.env.example").read_text(encoding="utf-8")
    assert timer.count("OnCalendar=") == 1
    assert "Persistent=true" in timer
    assert "infrastructure/staging/backup.py" in service
    assert "ports:" not in service
    assert "replace-with-a-long-random-string" in example
    assert "AKIA" not in example
    script = (staging / "backup.py").read_text(encoding="utf-8")
    assert "pg_dump" in script
    assert "/var/lib/postgresql/data" not in script
