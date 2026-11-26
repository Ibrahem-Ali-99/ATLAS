"""Create a production backup.

Postgres is dumped while it is running. Upload, model, and n8n files are
archived after n8n is stopped. The archive does not contain the Compose env
file. A placeholder or empty passphrase is refused, and an upload without
encryption is refused by the shared backup rules.
"""

from __future__ import annotations

import importlib.util
import os
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


_backup = _staging("atlas_staging_backup", "backup.py")
_contract = _staging("atlas_staging_backup_contract", "backup_contract.py")
_secrets = _staging("atlas_staging_backup_secrets", "backup_secrets.py")
BackupFailed = _backup.BackupFailed
create_backup = _backup.create_backup
BackupContractError = _contract.BackupContractError
SecretStoreError = _secrets.SecretStoreError
resolve_passphrase = _secrets.resolve

COMPOSE_FILE = ROOT / "infrastructure" / "compose.production.yaml"
DEFAULT_ENV = ROOT / "infrastructure" / "production" / ".env"
DEFAULT_DIR = ROOT / "infrastructure" / "production" / "backups"
KEYS_NOT_IN_ARCHIVE = (
    "PRODUCTION_SECRET_KEY",
    "PRODUCTION_CREDENTIAL_ENCRYPTION_KEYS",
    "PRODUCTION_POSTGRES_PASSWORD",
    "PRODUCTION_N8N_ENCRYPTION_KEY",
    "PRODUCTION_LLM_API_KEY",
    "ATLAS_BACKUP_PASSPHRASE",
    "AWS_SECRET_ACCESS_KEY",
)


def passphrase_is_usable(value: str) -> bool:
    lowered = value.lower()
    markers = ("replace-with", "change-me", "changeme", "dev-only")
    return len(value) >= 16 and not any(marker in lowered for marker in markers)


def main() -> int:
    project = os.environ.get("ATLAS_BACKUP_PROJECT", "atlas-production")
    env_file = Path(os.environ.get("ATLAS_COMPOSE_ENV", DEFAULT_ENV))
    backup_dir = Path(os.environ.get("ATLAS_BACKUP_DIR", DEFAULT_DIR))
    keep = int(os.environ.get("ATLAS_BACKUP_KEEP", "14"))
    try:
        passphrase = resolve_passphrase()
        if not passphrase_is_usable(passphrase):
            print("backup_refused passphrase", file=sys.stderr)
            return 2
        line = create_backup(
            project=project,
            env_file=env_file,
            backup_dir=backup_dir,
            keep=keep,
            passphrase=passphrase,
            s3_uri=os.environ.get("ATLAS_BACKUP_S3_URI", ""),
            s3_endpoint=os.environ.get("ATLAS_BACKUP_S3_ENDPOINT", ""),
            access_key=os.environ.get("AWS_ACCESS_KEY_ID", ""),
            secret_key=os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
            compose_file=COMPOSE_FILE,
            postgres_user_key="PRODUCTION_POSTGRES_USER",
            keys_not_in_archive=KEYS_NOT_IN_ARCHIVE,
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
