"""Inspect the Alembic chain without connecting to a database."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[2] / "apps" / "api" / "alembic" / "versions"
REVISION = re.compile(r'^revision(?:\s*:\s*[^=]+)?\s*=\s*"([^"]+)"', re.M)
DOWN = re.compile(r'^down_revision(?:\s*:\s*[^=]+)?\s*=\s*(?:None|"([^"]+)")', re.M)


@dataclass(frozen=True)
class MigrationReport:
    head: str
    revisions: int
    irreversible: tuple[str, ...]
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def inspect_tree(directory: Path = VERSIONS) -> MigrationReport:
    problems: list[str] = []
    parents: dict[str, str | None] = {}
    irreversible: list[str] = []
    if not directory.is_dir():
        return MigrationReport("", 0, (), ("migration directory is missing",))
    for path in sorted(directory.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        revision_match = REVISION.search(text)
        down_match = DOWN.search(text)
        if revision_match is None or down_match is None:
            problems.append(f"{path.name} does not declare a revision")
            continue
        revision = revision_match.group(1)
        if revision in parents:
            problems.append(f"duplicate revision {revision}")
        parents[revision] = down_match.group(1)
        if "def upgrade(" not in text or "def downgrade(" not in text:
            problems.append(f"{revision} is missing upgrade or downgrade")
        if "cannot be removed safely" in _downgrade_body(text):
            irreversible.append(revision)
    roots = [revision for revision, parent in parents.items() if parent is None]
    children: dict[str | None, list[str]] = {}
    for revision, parent in parents.items():
        children.setdefault(parent, []).append(revision)
    if len(roots) != 1:
        problems.append("the migration chain needs exactly one root")
    branched = [parent for parent, kids in children.items() if parent is not None and len(kids) > 1]
    if branched:
        problems.append("the migration chain branches at " + ", ".join(sorted(str(item) for item in branched)))
    head = ""
    if len(roots) == 1:
        cursor: str | None = roots[0]
        seen = 0
        while cursor is not None:
            seen += 1
            nxt = children.get(cursor, [])
            if len(nxt) > 1:
                break
            if not nxt:
                head = cursor
                break
            cursor = nxt[0]
        if seen != len(parents):
            problems.append("the migration chain is not a single line")
        missing_parents = sorted(
            parent for parent in parents.values() if parent is not None and parent not in parents
        )
        if missing_parents:
            problems.append("missing parent revisions: " + ", ".join(missing_parents))
    return MigrationReport(head, len(parents), tuple(sorted(irreversible)), tuple(problems))


def _downgrade_body(text: str) -> str:
    start = text.find("def downgrade(")
    if start < 0:
        return ""
    lines = text[start:].splitlines()
    body = [lines[0]]
    for line in lines[1:]:
        if line.startswith("def "):
            break
        body.append(line)
    return "\n".join(body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versions", type=Path, default=VERSIONS)
    args = parser.parse_args()
    report = inspect_tree(args.versions)
    for problem in report.problems:
        print(f"Blocked: {problem}")
    if report.problems:
        return 2
    manual = ",".join(report.irreversible) if report.irreversible else "none"
    print(
        f"migration_ok head={report.head} revisions={report.revisions} manual_downgrade={manual}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
