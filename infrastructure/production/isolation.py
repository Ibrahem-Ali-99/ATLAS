"""Names the production drills are allowed to create and remove."""

from __future__ import annotations

import subprocess

DRILL_PREFIX = "atlas-prod-drill"
IMAGE_PREFIX = "atlas-prod-image-proof"
LIVE_MARKERS = (
    "atlas-postgres-1",
    "atlas-mailpit-1",
    "atlas-n8n-1",
    "atlas-staging-postgres-1",
    "atlas-staging-api-1",
    "atlas-staging-caddy-1",
    "atlas-staging-n8n-1",
    "atlas-staging-ollama-1",
    "atlas-staging-web-1",
    "atlas-staging-mailpit-1",
)


def assert_owned(name: str) -> None:
    if not (name.startswith(DRILL_PREFIX) or name.startswith(IMAGE_PREFIX)):
        raise RuntimeError(f"refusing to touch {name}")


def live_markers() -> dict[str, str]:
    found: dict[str, str] = {}
    for name in LIVE_MARKERS:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.Id}} {{.State.StartedAt}}", name],
            capture_output=True,
            text=True,
            check=False,
        )
        found[name] = result.stdout.strip() if result.returncode == 0 else "absent"
    return found
