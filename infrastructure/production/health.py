"""Report Compose service health without restarting anything."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

COMPOSE_FILE = Path(__file__).resolve().parents[1] / "compose.production.yaml"
ENV_FILE = Path(__file__).resolve().parent / ".env"
EXPECTED = ("caddy", "web", "api", "postgres", "mailpit", "n8n", "ollama")


def summarize(rows: list[dict[str, object]]) -> list[str]:
    by_service = {str(row.get("Service")): row for row in rows}
    issues: list[str] = []
    for name in EXPECTED:
        row = by_service.get(name)
        if row is None:
            issues.append(f"{name} is not running")
            continue
        health = str(row.get("Health") or "")
        state = str(row.get("State") or "")
        if health != "healthy" or state != "running":
            issues.append(f"{name} is {state or 'unknown'} ({health or 'no health'})")
    embedding = by_service.get("embedding-model")
    if embedding is not None:
        exit_code = embedding.get("ExitCode")
        state = str(embedding.get("State") or "")
        if state == "running":
            issues.append("embedding-model is still running")
        elif exit_code not in (0, "0", None) and state not in {"exited", ""}:
            issues.append(f"embedding-model exited {exit_code}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="atlas-production")
    parser.add_argument("--compose-file", type=Path, default=COMPOSE_FILE)
    parser.add_argument("--env-file", type=Path, default=ENV_FILE)
    args = parser.parse_args()
    if args.project in {"atlas", "atlas-staging"}:
        print("Refusing to inspect a shared project from the production health command.")
        return 2
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            args.project,
            "--project-directory",
            str(COMPOSE_FILE.parent),
            "--env-file",
            str(args.env_file),
            "-f",
            str(args.compose_file),
            "ps",
            "--all",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print("health_failed compose_ps")
        return 2
    rows: list[dict[str, object]] = []
    for line in result.stdout.splitlines():
        if line.startswith("{"):
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    issues = summarize(rows)
    for issue in issues:
        print(f"Blocked: {issue}")
    if issues:
        return 2
    print("health_ok services=" + ",".join(EXPECTED))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
