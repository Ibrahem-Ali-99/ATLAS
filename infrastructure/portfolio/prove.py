"""Boot the portfolio stack on unused local ports, then remove it.

Does not stop or delete containers from any other project. Seed passwords are
read from the developer environment and are not written to the result.
"""

from __future__ import annotations

import json
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from apply_demo import SEED_KEYS, apply_demo  # noqa: E402
from backup import create_backup, restore_archive  # noqa: E402
from preflight import problems, read_env  # noqa: E402
from project import compose_command  # noqa: E402
from smoke import problems as smoke_problems  # noqa: E402

PROJECT = "atlas-portfolio-proof"
REPORT = ROOT / "var" / "portfolio-proof" / "result.json"


def free_port(port: int) -> bool:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def choose_ports() -> tuple[int, int]:
    for http_port, https_port in ((19380, 19343), (19580, 19543), (19680, 19643)):
        if free_port(http_port) and free_port(https_port):
            return http_port, https_port
    raise SystemExit("No isolated port pair was free.")


def snapshot(prefix: str) -> dict[str, str]:
    listed = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    found: dict[str, str] = {}
    for name in listed.stdout.splitlines():
        if not name or name.startswith(prefix):
            continue
        inspected = subprocess.run(
            ["docker", "inspect", "-f", "{{.Id}} {{.State.StartedAt}}", name],
            check=False,
            capture_output=True,
            text=True,
        )
        found[name] = inspected.stdout.strip()
    return found


def wait_healthy(service: str, timeout: int) -> bool:
    name = f"{PROJECT}-{service}-1"
    deadline = time.time() + timeout
    while time.time() < deadline:
        inspected = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Health.Status}}", name],
            check=False,
            capture_output=True,
            text=True,
        )
        if inspected.stdout.strip() == "healthy":
            return True
        time.sleep(5)
    return False


def sql(statement: str) -> tuple[int, str]:
    result = subprocess.run(
        [
            "docker",
            "exec",
            f"{PROJECT}-postgres-1",
            "psql",
            "-U",
            "atlas",
            "-d",
            "atlas_portfolio",
            "-tA",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            statement,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout.strip()


def main() -> int:
    if not PROJECT.startswith("atlas-portfolio-proof"):
        raise SystemExit("refusing to run")
    before = snapshot(PROJECT)
    http_port, https_port = choose_ports()
    proof_dir = ROOT / "var" / "portfolio-proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    env_file = proof_dir / "compose.env"
    secret = secrets.token_hex(32)
    password = secrets.token_hex(24)
    key = secrets.token_hex(32)
    origin = f"https://atlas.localhost:{https_port}"
    env_file.write_text(
        "\n".join(
            [
                "PORTFOLIO_ENVIRONMENT=development",
                "PORTFOLIO_PUBLIC_DEMO=true",
                f"PORTFOLIO_SECRET_KEY={secret}",
                f"PORTFOLIO_CREDENTIAL_ENCRYPTION_KEYS=demo-01={key}",
                "PORTFOLIO_POSTGRES_USER=atlas",
                f"PORTFOLIO_POSTGRES_PASSWORD={password}",
                "PORTFOLIO_POSTGRES_DB=atlas_portfolio",
                "PORTFOLIO_HOST=atlas.localhost",
                f"PORTFOLIO_HTTP_PORT={http_port}",
                f"PORTFOLIO_HTTPS_PORT={https_port}",
                f"PORTFOLIO_CORS_ORIGINS={origin}",
                f"PORTFOLIO_CAMPAIGN_PUBLIC_URL={origin}",
                "PORTFOLIO_LOG_LEVEL=INFO",
                "PORTFOLIO_COOKIE_SECURE=true",
                "PORTFOLIO_LLM_API_KEY=",
                "PORTFOLIO_EMBEDDING_API_KEY=",
                "PORTFOLIO_STRIPE_SECRET_KEY=",
                "PORTFOLIO_GOOGLE_CALENDAR_CLIENT_SECRET=",
                "",
            ]
        ),
        encoding="utf-8",
    )
    result: dict[str, object] = {
        "http_port": http_port,
        "https_port": https_port,
        "preflight": problems(read_env(env_file)) == [],
    }
    started = False
    try:
        if not result["preflight"]:
            return 1
        up = subprocess.run(
            [*compose_command(PROJECT, env_file), "up", "-d", "--build"],
            cwd=ROOT,
            check=False,
        )
        started = True
        result["compose_up"] = up.returncode == 0
        if up.returncode != 0:
            return 1
        names = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={PROJECT}", "--format", "{{.Names}}"],
            check=False,
            capture_output=True,
            text=True,
        )
        owned = [name for name in names.stdout.splitlines() if name]
        result["owned_names"] = owned
        if not owned or any(not name.startswith(PROJECT) for name in owned):
            result["owned_names_ok"] = False
            return 1
        result["owned_names_ok"] = True
        result["caddy_healthy"] = wait_healthy("caddy", 900)
        if not result["caddy_healthy"]:
            return 1
        published = []
        for service in ("postgres", "mailpit", "api", "web"):
            ports = subprocess.run(
                ["docker", "port", f"{PROJECT}-{service}-1"],
                check=False,
                capture_output=True,
                text=True,
            )
            if ports.stdout.strip():
                published.append(service)
        result["unpublished_private_services"] = published == []
        ca = proof_dir / "ca.crt"
        copied = subprocess.run(
            ["docker", "cp", f"{PROJECT}-caddy-1:/data/caddy/pki/authorities/local/root.crt", str(ca)],
            check=False,
        )
        result["ca_copied"] = copied.returncode == 0
        if copied.returncode != 0:
            return 1
        issues = smoke_problems(origin, str(ca), f"http://atlas.localhost:{http_port}")
        result["smoke"] = issues
        if issues:
            return 1
        developer = read_env(ROOT / ".env")
        seed = {key: developer.get(key, "") for key in SEED_KEYS}
        apply_demo(PROJECT, env_file, seed)
        ready = False
        status = ""
        for _ in range(24):
            code, status = sql(
                "SELECT status FROM documents WHERE title = 'Bonded warehousing overview' LIMIT 1"
            )
            if code == 0 and status == "ready":
                ready = True
                break
            time.sleep(5)
        result["document_ready"] = ready
        result["document_status"] = status
        if not ready:
            return 1
        _, harbor = sql("SELECT count(*) FROM companies WHERE name = 'Harbor & Co.'")
        result["harbor_before"] = harbor
        if harbor in {"", "0"}:
            result["harbor_restored"] = False
            return 1
        archive = proof_dir / "portfolio-proof.tar.gz"
        create_backup(PROJECT, archive)
        sql("UPDATE companies SET name = 'Removed proof' WHERE name = 'Harbor & Co.'")
        _, renamed = sql("SELECT count(*) FROM companies WHERE name = 'Removed proof'")
        result["renamed_before_restore"] = renamed
        restore_archive(PROJECT, env_file, archive)
        result["api_healthy_after_restore"] = wait_healthy("api", 180)
        _, restored = sql("SELECT count(*) FROM companies WHERE name = 'Harbor & Co.'")
        _, removed = sql("SELECT count(*) FROM companies WHERE name = 'Removed proof'")
        _, foreign = sql(
            "SELECT count(*) FROM companies c "
            "JOIN organizations o ON o.id = c.organization_id "
            "WHERE c.name = 'Harbor & Co.' AND o.slug <> 'atlas-demo'"
        )
        result["harbor_restored"] = restored == harbor and removed == "0"
        result["harbor_stays_in_atlas_demo"] = foreign == "0"
        return 0 if result["harbor_restored"] and result["harbor_stays_in_atlas_demo"] else 1
    except (SystemExit, Exception) as exc:
        detail = getattr(exc, "reason", None)
        if detail is None:
            detail = getattr(exc, "step", None)
        if detail is None:
            detail = exc.code if isinstance(exc, SystemExit) else exc.__class__.__name__
        text = str(detail)
        if "://" in text or len(text) > 400:
            text = exc.__class__.__name__
        result["error"] = text
        return 1
    finally:
        after = snapshot(PROJECT)
        changed = sorted(
            (set(before) ^ set(after))
            | {name for name in before.keys() & after.keys() if before[name] != after[name]}
        )
        result["changed_containers"] = changed
        watched = [name for name in changed if name.startswith("atlas-")]
        result["live_projects_unchanged"] = watched == []
        if started:
            subprocess.run(
                [*compose_command(PROJECT, env_file), "down", "-v", "--remove-orphans"],
                cwd=ROOT,
                check=False,
            )
        env_file.unlink(missing_ok=True)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({key: value for key, value in result.items() if key != "owned_names"}))


if __name__ == "__main__":
    raise SystemExit(main())
