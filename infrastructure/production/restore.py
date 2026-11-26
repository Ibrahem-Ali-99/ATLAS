"""Restore a production backup into an isolated Compose project.

Refuses the development, staging, and production project names. Decrypts the
archive, checks every SHA-256, loads each dump, and extracts upload, model,
and n8n files into fresh volumes. The caller starts the application afterward.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "infrastructure" / "staging"
sys.path.insert(0, str(STAGING))


def _staging(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, STAGING / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"missing {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_contract = _staging("atlas_staging_backup_contract", "backup_contract.py")
_secrets = _staging("atlas_staging_backup_secrets", "backup_secrets.py")
_restore = _staging("atlas_staging_restore", "restore.py")
BackupContractError = _contract.BackupContractError
SecretStoreError = _secrets.SecretStoreError
resolve_passphrase = _secrets.resolve
RestoreFailed = _restore.RestoreFailed
restore_backup = _restore.restore_backup
verify_archive = _restore.verify_archive
verify_restored_uploads = _restore.verify_restored_uploads

COMPOSE_FILE = ROOT / "infrastructure" / "compose.production.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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
                compose_file=COMPOSE_FILE,
                postgres_user_key="PRODUCTION_POSTGRES_USER",
            )
        else:
            line = restore_backup(
                project=args.project,
                env_file=args.env_file,
                archive=args.archive,
                passphrase=passphrase,
                compose_file=COMPOSE_FILE,
                postgres_user_key="PRODUCTION_POSTGRES_USER",
            )
    except BackupContractError as exc:
        print(exc.reason, file=sys.stderr)
        return 2
    except RestoreFailed as exc:
        print(exc.reason, file=sys.stderr)
        return 2
    except (OSError, SecretStoreError) as exc:
        print(f"restore_failed {exc.__class__.__name__}", file=sys.stderr)
        return 1
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
