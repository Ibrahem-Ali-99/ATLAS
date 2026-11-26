"""Check the production Compose file without starting containers."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

COMPOSE_FILE = Path(__file__).resolve().parents[1] / "compose.production.yaml"
REQUIRED_SERVICES = (
    "caddy",
    "web",
    "api",
    "postgres",
    "mailpit",
    "n8n",
    "ollama",
    "embedding-model",
)
HEALTHCHECKED = ("caddy", "web", "api", "postgres", "mailpit", "n8n", "ollama")
LIMITED = {
    "caddy": "128M",
    "web": "512M",
    "api": "1536M",
    "postgres": "1024M",
    "mailpit": "128M",
    "n8n": "768M",
    "ollama": "1280M",
    "embedding-model": "512M",
}


def service_blocks(text: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    in_services = False
    for line in text.splitlines():
        if line == "services:":
            in_services = True
            continue
        if not in_services:
            continue
        if line and not line.startswith(" "):
            break
        if re.fullmatch(r"  [a-z0-9-]+:", line):
            if current is not None:
                blocks[current] = "\n".join(buffer)
            current = line.strip()[:-1]
            buffer = []
            continue
        buffer.append(line)
    if current is not None:
        blocks[current] = "\n".join(buffer)
    return blocks


def problems(text: str) -> list[str]:
    issues: list[str] = []
    blocks = service_blocks(text)
    missing = [name for name in REQUIRED_SERVICES if name not in blocks]
    if missing:
        issues.append("missing services: " + ", ".join(missing))
    for name, block in blocks.items():
        if name != "caddy" and re.search(r"(?m)^    ports:", block):
            issues.append(f"{name} publishes a host port")
        if "no-new-privileges:true" not in block:
            issues.append(f"{name} does not keep new privileges off")
        if "logging: *default-logging" not in block and 'max-size: "10m"' not in block:
            issues.append(f"{name} does not rotate container logs")
        if LIMITED.get(name) and f"memory: {LIMITED[name]}" not in block:
            issues.append(f"{name} is missing its memory limit")
    if "caddy" in blocks and not re.search(r"(?m)^    ports:", blocks["caddy"]):
        issues.append("caddy does not publish HTTP")
    for name in HEALTHCHECKED:
        block = blocks.get(name, "")
        if "healthcheck:" not in block:
            issues.append(f"{name} has no health check")
    _dependencies(blocks, issues)
    if "postgres/init" in text:
        issues.append("production Postgres must not create development databases")
    if re.search(r"POSTGRES_PASSWORD:-\s*atlas", text) or "replace-with-a-long-random-string" in text:
        issues.append("production Compose must not embed a default credential")
    if 'ATLAS_ENVIRONMENT: production' not in text:
        issues.append("the API environment must be hardcoded to production")
    if 'ATLAS_COOKIE_SECURE: "true"' not in text or 'ATLAS_PUBLIC_DEMO: "false"' not in text:
        issues.append("production cookies must be secure and the public demo must be off")
    if "pgvector/pgvector:pg17" not in text:
        issues.append("Postgres must be the pgvector image")
    if "n8nio/n8n:2.49.6" not in text:
        issues.append("n8n must stay on the pinned 2.49.6 image")
    if "ATLAS_PUBLIC_API_URL: http://api:8000" not in text:
        issues.append("callbacks must use the private API address")
    if 'max-size: "10m"' not in text or "max-file: \"5\"" not in text:
        issues.append("container logs are not limited to five 10 MB files")
    return issues


def _dependencies(blocks: dict[str, str], issues: list[str]) -> None:
    expected = {
        "caddy": ("api:\n        condition: service_healthy", "web:\n        condition: service_healthy"),
        "web": ("api:\n        condition: service_healthy",),
        "api": (
            "postgres:\n        condition: service_healthy",
            "mailpit:\n        condition: service_healthy",
            "embedding-model:\n        condition: service_completed_successfully",
        ),
        "embedding-model": ("ollama:\n        condition: service_healthy",),
    }
    for service, edges in expected.items():
        block = blocks.get(service, "")
        for edge in edges:
            if edge not in block:
                issues.append(f"{service} is missing dependency {edge.split(':', 1)[0]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", type=Path, default=COMPOSE_FILE)
    args = parser.parse_args()
    try:
        issues = problems(args.compose_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        print("Production Compose file could not be read.")
        return 2
    for issue in issues:
        print(f"Blocked: {issue}")
    if issues:
        return 2
    print("Production Compose contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
