"""Boot the production Compose file on unused local ports, then remove it.

Volume names are overridden so the proof cannot replace a real production volume.
It does not stop containers from any other project.
"""

from __future__ import annotations

import json
import secrets
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infrastructure" / "portfolio"))

from smoke import problems as smoke_problems  # noqa: E402

PROJECT = "atlas-prod-stack-proof"
COMPOSE = ROOT / "infrastructure" / "compose.production.yaml"
REPORT = ROOT / "var" / "production-stack-proof" / "result.json"
VOLUME_KEYS = (
    "atlas_production_caddy_data",
    "atlas_production_caddy_config",
    "atlas_production_postgres_data",
    "atlas_production_uploads",
    "atlas_production_models",
    "atlas_production_mailpit_data",
    "atlas_production_n8n_data",
    "atlas_production_ollama_data",
)


def free_port(port: int) -> bool:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def choose_ports() -> tuple[int, int]:
    for http_port, https_port in ((19480, 19443), (19780, 19743), (19880, 19843)):
        if free_port(http_port) and free_port(https_port):
            return http_port, https_port
    raise SystemExit("No isolated port pair was free.")


def snapshot() -> dict[str, str]:
    listed = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    found: dict[str, str] = {}
    for name in listed.stdout.splitlines():
        if not name or name.startswith(PROJECT):
            continue
        inspected = subprocess.run(
            ["docker", "inspect", "-f", "{{.Id}} {{.State.StartedAt}}", name],
            check=False,
            capture_output=True,
            text=True,
        )
        found[name] = inspected.stdout.strip()
    return found


def volumes() -> set[str]:
    listed = subprocess.run(["docker", "volume", "ls", "-q"], check=False, capture_output=True, text=True)
    return {line for line in listed.stdout.splitlines() if line}


def wait_healthy(timeout: int) -> bool:
    import time

    name = f"{PROJECT}-caddy-1"
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


def main() -> int:
    if not PROJECT.startswith("atlas-prod-stack-proof"):
        raise SystemExit("refusing to run")
    running = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if any(name.startswith("atlas-production") for name in running.stdout.splitlines()):
        raise SystemExit("A production project container is already present. The proof will not touch it.")
    before = snapshot()
    before_volumes = volumes()
    http_port, https_port = choose_ports()
    proof_dir = REPORT.parent
    proof_dir.mkdir(parents=True, exist_ok=True)
    env_file = proof_dir / "compose.env"
    override = proof_dir / "volumes.yml"
    secret = secrets.token_hex(32)
    password = secrets.token_hex(24)
    key = secrets.token_hex(32)
    n8n_key = secrets.token_hex(32)
    origin = f"https://atlas.localhost:{https_port}"
    env_file.write_text(
        "\n".join(
            [
                "PRODUCTION_ENVIRONMENT=production",
                "PRODUCTION_PUBLIC_DEMO=false",
                "PRODUCTION_COOKIE_SECURE=true",
                "PRODUCTION_LOG_LEVEL=INFO",
                f"PRODUCTION_SECRET_KEY={secret}",
                "PRODUCTION_POSTGRES_USER=atlas",
                f"PRODUCTION_POSTGRES_PASSWORD={password}",
                "PRODUCTION_POSTGRES_DB=atlas",
                f"PRODUCTION_N8N_ENCRYPTION_KEY={n8n_key}",
                f"PRODUCTION_CREDENTIAL_ENCRYPTION_KEYS=proof-01={key}",
                "PRODUCTION_HOST=atlas.localhost",
                f"PRODUCTION_HTTP_PORT={http_port}",
                f"PRODUCTION_HTTPS_PORT={https_port}",
                f"PRODUCTION_CORS_ORIGINS={origin}",
                f"PRODUCTION_CAMPAIGN_PUBLIC_URL={origin}",
                "PRODUCTION_LLM_PROVIDER=groq",
                f"PRODUCTION_LLM_API_KEY={secrets.token_hex(24)}",
                "PRODUCTION_LLM_MODEL=llama-3.3-70b-versatile",
                "PRODUCTION_EMBEDDING_PROVIDER=ollama",
                "PRODUCTION_EMBEDDING_BASE_URL=http://ollama:11434/v1",
                "PRODUCTION_EMBEDDING_DIMENSIONS=768",
                "PRODUCTION_EMAIL_MODE=sandbox",
                "PRODUCTION_SMTP_HOST=mailpit",
                "PRODUCTION_BILLING_PROVIDER=sandbox",
                "PRODUCTION_WHATSAPP_LIVE_ENABLED=false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    override.write_text(
        "volumes:\n"
        + "".join(
            f"  {logical}:\n    name: {PROJECT}-{logical.removeprefix('atlas_production_')}\n"
            for logical in VOLUME_KEYS
        ),
        encoding="utf-8",
    )
    compose = [
        "docker",
        "compose",
        "--project-name",
        PROJECT,
        "-f",
        str(COMPOSE),
        "-f",
        str(override),
        "--env-file",
        str(env_file),
    ]
    preflight = subprocess.run(
        [sys.executable, str(ROOT / "infrastructure" / "production" / "preflight.py"), "--env-file", str(env_file)],
        check=False,
        capture_output=True,
        text=True,
    )
    result: dict[str, object] = {
        "http_port": http_port,
        "https_port": https_port,
        "preflight": preflight.returncode == 0,
    }
    started = False
    try:
        if preflight.returncode != 0:
            result["preflight_output"] = [
                line for line in preflight.stdout.splitlines() if line.startswith("Blocked:")
            ]
            return 1
        up = subprocess.run([*compose, "up", "-d", "--build"], cwd=ROOT, check=False)
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
        result["owned_names_ok"] = bool(owned) and all(name.startswith(PROJECT) for name in owned)
        if not result["owned_names_ok"]:
            return 1
        result["caddy_healthy"] = wait_healthy(1200)
        if not result["caddy_healthy"]:
            logs = subprocess.run(
                ["docker", "logs", "--tail", "40", f"{PROJECT}-embedding-model-1"],
                check=False,
                capture_output=True,
                text=True,
            )
            result["embedding_log_tail"] = [
                line for line in (logs.stdout + logs.stderr).splitlines() if "KEY" not in line.upper()
            ][-15:]
            return 1
        private = []
        for service in ("postgres", "mailpit", "api", "web", "n8n", "ollama"):
            ports = subprocess.run(
                ["docker", "port", f"{PROJECT}-{service}-1"],
                check=False,
                capture_output=True,
                text=True,
            )
            if ports.stdout.strip():
                private.append(service)
        result["unpublished_private_services"] = private == []
        ca = proof_dir / "ca.crt"
        copied = subprocess.run(
            ["docker", "cp", f"{PROJECT}-caddy-1:/data/caddy/pki/authorities/local/root.crt", str(ca)],
            check=False,
        )
        if copied.returncode != 0:
            result["ca_copied"] = False
            return 1
        issues = smoke_problems(origin, str(ca), f"http://atlas.localhost:{http_port}")
        result["smoke"] = issues
        return 0 if not issues and result["unpublished_private_services"] else 1
    finally:
        after = snapshot()
        changed = sorted(
            (set(before) ^ set(after))
            | {name for name in before.keys() & after.keys() if before[name] != after[name]}
        )
        result["changed_containers"] = [name for name in changed if name.startswith("atlas-")]
        result["live_projects_unchanged"] = result["changed_containers"] == []
        if started:
            subprocess.run([*compose, "down", "-v", "--remove-orphans"], cwd=ROOT, check=False)
        removed = before_volumes - volumes()
        result["removed_only_proof_volumes"] = all(name.startswith(PROJECT) for name in removed)
        env_file.unlink(missing_ok=True)
        override.unlink(missing_ok=True)
        REPORT.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))


if __name__ == "__main__":
    raise SystemExit(main())
