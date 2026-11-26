"""Provision the fictional demo records, then restart the portfolio API.

Seed passwords come from the process environment. They are not printed and they
are not written to the portfolio env file. The running API stays a public demo;
this one-off is the only process allowed to write the prepared rows.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from preflight import read_env
from project import LIVE_PROJECT, ProjectRefused, assert_project, compose_command

SEED_KEYS = (
    "SEED_ADMIN_EMAIL",
    "SEED_ADMIN_PASSWORD",
    "SEED_ADMIN_NAME",
    "SEED_STAFF_EMAIL",
    "SEED_STAFF_PASSWORD",
    "SEED_STAFF_NAME",
    "SEED_OUTSIDER_EMAIL",
    "SEED_OUTSIDER_PASSWORD",
    "SEED_OUTSIDER_NAME",
)


def seed_from_environ() -> dict[str, str]:
    return {key: os.environ.get(key, "") for key in SEED_KEYS}


def apply_demo(project: str, env_file: Path, seed: dict[str, str]) -> None:
    assert_project(project)
    missing = [key for key in SEED_KEYS if not seed.get(key, "").strip()]
    if missing:
        raise SystemExit("Missing " + ", ".join(missing) + ". Export them in this shell only.")
    settings = read_env(env_file)
    user = settings.get("PORTFOLIO_POSTGRES_USER", "atlas")
    password = settings.get("PORTFOLIO_POSTGRES_PASSWORD", "")
    if not password:
        raise SystemExit("The portfolio env file has no database password.")
    url = f"postgresql+psycopg://{user}:{password}@postgres:5432/atlas_portfolio"
    overlay = {
        "ATLAS_PORTFOLIO_DATABASE_URL": url,
        "ATLAS_DATABASE_URL": url,
        "ATLAS_PORTFOLIO_STORAGE_DIR": "/var/lib/atlas/portfolio-docs",
        "ATLAS_STORAGE_DIR": "/tmp/atlas-seed-guard",
        **seed,
    }
    command = [
        *compose_command(project, env_file),
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
    ]
    for key, value in {
        "ATLAS_PORTFOLIO_DEMO": "apply",
        "ATLAS_PUBLIC_DEMO": "false",
        "ATLAS_ENVIRONMENT": "development",
        "ATLAS_LLM_PROVIDER": "double",
        "ATLAS_LLM_API_KEY": "",
        "ATLAS_EMBEDDING_PROVIDER": "double",
        "ATLAS_EMBEDDING_API_KEY": "",
        "ATLAS_EMAIL_MODE": "sandbox",
        "ATLAS_EMAIL_LIVE_ENABLED": "false",
        "ATLAS_CAMPAIGN_LIVE_ENABLED": "false",
        "ATLAS_WHATSAPP_LIVE_ENABLED": "false",
        "ATLAS_N8N_LEAD_WEBHOOK_URL": "",
        "ATLAS_BILLING_PROVIDER": "sandbox",
        "ATLAS_STRIPE_SECRET_KEY": "",
        "ATLAS_GOOGLE_CALENDAR_CLIENT_SECRET": "",
        **overlay,
    }.items():
        command.extend(["-e", f"{key}={value}"])
    command.extend(["api", "-m", "app.scripts.portfolio_demo"])
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        safe = [
            line
            for line in (completed.stderr or "").splitlines()
            if "://" not in line and password not in line and not any(value and value in line for value in seed.values())
        ]
        detail = " ".join(safe)[-240:] or f"exit {completed.returncode}"
        raise SystemExit(detail)
    restarted = subprocess.run([*compose_command(project, env_file), "restart", "api"], check=False)
    if restarted.returncode != 0:
        raise SystemExit("The records were written, but the API did not restart to index them.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=LIVE_PROJECT)
    parser.add_argument("--env-file", type=Path, default=Path("infrastructure/portfolio/.env"))
    args = parser.parse_args()
    try:
        apply_demo(args.project, args.env_file, seed_from_environ())
    except ProjectRefused:
        print("Refusing to write demo records into that project.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
