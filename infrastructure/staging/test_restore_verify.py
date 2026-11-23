import os
import subprocess
import sys
from pathlib import Path

import pytest
from backup import CIPHER_PROGRAM, pack
from backup_contract import build_manifest, file_record, write_manifest
from restore import RestoreFailed, open_validated_archive, verify_archive


def make_archive(root: Path) -> Path:
    work = root / "work"
    work.mkdir()
    for name in ("postgres-atlas.dump", "globals.sql", "uploads.tar", "models.tar", "n8n.tar"):
        (work / name).write_bytes(name.encode())
    names = ("postgres-atlas.dump", "globals.sql", "uploads.tar", "models.tar", "n8n.tar")
    records = {name: file_record(work / name) for name in names}
    write_manifest(
        work / "manifest.json",
        build_manifest(
            created_at="2026-01-01T00:00:00Z",
            project="atlas-restore-test",
            records=records,
        ),
    )
    plain = root / "archive.tar.gz"
    encrypted = root / "archive.tar.gz.enc"
    pack(work, plain)
    decrypted_result = subprocess.run(
        [sys.executable, "-c", CIPHER_PROGRAM, "enc"],
        input=plain.read_bytes(),
        capture_output=True,
        env={**os.environ, "ATLAS_BACKUP_PASSPHRASE": "test-passphrase"},
        check=True,
    )
    encrypted.write_bytes(result.stdout)
    return encrypted


def test_verify_only_round_trip(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)

    result = verify_archive(archive=archive, passphrase="test-passphrase")

    assert result.startswith("verify_ok archive=archive.tar.gz.enc")
    decrypted = tmp_path / "decrypted.tar.gz"
    result = subprocess.run(
        [sys.executable, "-c", CIPHER_PROGRAM, "dec"],
        input=archive.read_bytes(),
        capture_output=True,
        env={**os.environ, "ATLAS_BACKUP_PASSPHRASE": "test-passphrase"},
        check=True,
    )
    decrypted.write_bytes(decrypted_result.stdout)
    with open_validated_archive(decrypted) as packed:
        assert "manifest.json" in packed.getnames()


def test_verify_only_rejects_corrupted_archive(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    data = bytearray(archive.read_bytes())
    data[-1] ^= 1
    archive.write_bytes(data)

    with pytest.raises(RestoreFailed, match="decrypt_failed"):
        verify_archive(archive=archive, passphrase="test-passphrase")


def test_verify_only_rejects_malformed_archive(tmp_path: Path) -> None:
    archive = tmp_path / "archive.tar.gz"
    archive.write_bytes(b"not-a-gzip")

    with pytest.raises(RestoreFailed, match="gzip_header"):
        verify_archive(archive=archive, passphrase="")
