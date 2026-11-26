"""Project names the portfolio backup and restore commands are allowed to touch."""

from __future__ import annotations

import re
from pathlib import Path

COMPOSE_FILE = Path(__file__).resolve().parents[1] / "compose.portfolio.yaml"
LIVE_PROJECT = "atlas-portfolio"
PROOF_PREFIX = "atlas-portfolio-proof"
REFUSED = frozenset(
    {
        "atlas",
        "atlas-staging",
        "atlas-production",
        "infrastructure",
        "titan",
        "legalstats",
    }
)
PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")


class ProjectRefused(Exception):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)


class BackupFailed(Exception):
    def __init__(self, step: str) -> None:
        self.step = step
        super().__init__(step)


def assert_project(name: str) -> str:
    if not PROJECT_RE.fullmatch(name) or name in REFUSED:
        raise ProjectRefused(name)
    if name != LIVE_PROJECT and not name.startswith(PROOF_PREFIX):
        raise ProjectRefused(name)
    return name


def compose_command(project: str, env_file: Path) -> list[str]:
    assert_project(project)
    return [
        "docker",
        "compose",
        "--project-name",
        project,
        "-f",
        str(COMPOSE_FILE),
        "--env-file",
        str(env_file),
    ]
