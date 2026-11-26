"""Prove the API image rejects unsafe production settings and can serve /ready.

Uses containers named atlas-prod-image-proof-*. The positive check keeps the
container on an internal network so it cannot reach provider APIs.
"""

from __future__ import annotations

import json
import secrets
import subprocess
import time
from pathlib import Path

from isolation import assert_owned, live_markers

ROOT = Path(__file__).resolve().parents[2]
RESULT = ROOT / "var" / "production-drill" / "startup.json"
IMAGE = "atlas-api:production-check"
NETWORK = "atlas-prod-image-proof"
POSTGRES = "atlas-prod-image-proof-pg"
API = "atlas-prod-image-proof-api"


def cleanup() -> None:
    for name in (API, POSTGRES):
        subprocess.run(["docker", "rm", "-f", assert_name(name)], capture_output=True, check=False)
    subprocess.run(["docker", "network", "rm", assert_name(NETWORK)], capture_output=True, check=False)


def assert_name(name: str) -> str:
    assert_owned(name)
    return name


def image_exists() -> bool:
    result = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, check=False)
    return result.returncode == 0


def run_unsafe(
    label: str, environment: dict[str, str], secret: str, expected: str
) -> dict[str, object]:
    command = ["docker", "run", "--rm", "--network", "none"]
    for key, value in environment.items():
        command.extend(["-e", f"{key}={value}"])
    command.append(IMAGE)
    result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    raw = result.stdout + result.stderr
    output = raw.replace(secret, "[redacted]")
    return {
        "label": label,
        "rejected": result.returncode != 0 and expected in raw and secret not in raw,
        "detail": output[-240:].strip(),
    }


def status_inside(path: str) -> int:
    script = (
        "import urllib.error, urllib.request\n"
        "try:\n"
        f"    response = urllib.request.urlopen('http://127.0.0.1:8000{path}', timeout=10)\n"
        "    print(response.status)\n"
        "except urllib.error.HTTPError as exc:\n"
        "    print(exc.code)\n"
    )
    result = subprocess.run(
        ["docker", "exec", assert_name(API), "python", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip().isdigit():
        raise RuntimeError(result.stderr[-200:] or "status_probe_failed")
    return int(result.stdout.strip())


def wait_healthy(timeout: int = 120) -> str:
    deadline = time.monotonic() + timeout
    status = ""
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{if .State.Health}}{{.State.Health.Status}}{{end}}", assert_name(API)],
            capture_output=True,
            text=True,
            check=False,
        )
        status = result.stdout.strip()
        if status == "healthy":
            return status
        if status == "unhealthy":
            return status
        time.sleep(2)
    return status or "missing"


def prove_ready(password: str) -> dict[str, object]:
    secret = secrets.token_hex(32)
    keyring = secrets.token_hex(32)
    subprocess.run(
        ["docker", "network", "create", "--internal", assert_name(NETWORK)],
        capture_output=True,
        check=False,
    )
    postgres = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            assert_name(POSTGRES),
            "--network",
            assert_name(NETWORK),
            "--network-alias",
            "postgres",
            "-e",
            "POSTGRES_USER=atlas",
            "-e",
            f"POSTGRES_PASSWORD={password}",
            "-e",
            "POSTGRES_DB=atlas",
            "pgvector/pgvector:pg17",
        ],
        capture_output=True,
        check=False,
    )
    if postgres.returncode != 0:
        raise RuntimeError("proof postgres did not start")
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        ready = subprocess.run(
            ["docker", "exec", assert_name(POSTGRES), "pg_isready", "-U", "atlas", "-d", "atlas"],
            capture_output=True,
            check=False,
        )
        if ready.returncode == 0:
            break
        time.sleep(2)
    else:
        raise RuntimeError("proof postgres did not become ready")
    api = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            assert_name(API),
            "--network",
            assert_name(NETWORK),
            "--security-opt",
            "no-new-privileges:true",
            "-e",
            "ATLAS_ENVIRONMENT=production",
            "-e",
            f"ATLAS_SECRET_KEY={secret}",
            "-e",
            f"ATLAS_CREDENTIAL_ENCRYPTION_KEYS=prod-01={keyring}",
            "-e",
            "ATLAS_COOKIE_SECURE=true",
            "-e",
            f"ATLAS_DATABASE_URL=postgresql+psycopg://atlas:{password}@postgres:5432/atlas",
            "-e",
            "ATLAS_CORS_ORIGINS=https://atlas.localhost",
            "-e",
            "ATLAS_LLM_PROVIDER=openai",
            "-e",
            "ATLAS_LLM_API_KEY=",
            "-e",
            "ATLAS_EMBEDDING_PROVIDER=ollama",
            "-e",
            "ATLAS_EMBEDDING_BASE_URL=http://ollama:11434/v1",
            "-e",
            "ATLAS_EMBEDDING_DIMENSIONS=768",
            IMAGE,
        ],
        capture_output=True,
        check=False,
    )
    if api.returncode != 0:
        raise RuntimeError("proof api did not start")
    status = wait_healthy()
    top = subprocess.run(["docker", "top", assert_name(API)], capture_output=True, text=True, check=False)
    identity = top.stdout.lower()
    return {
        "health_status": status,
        "docs_status": status_inside("/docs"),
        "ready_status": status_inside("/api/v1/ready"),
        "health_endpoint": status_inside("/api/v1/health"),
        "server_user_dropped": "10001" in identity or "atlas" in identity,
        "secret_absent_from_process_list": secret not in top.stdout and password not in top.stdout,
    }


def main() -> int:
    if not image_exists():
        print("startup_failed image_missing")
        return 2
    before = live_markers()
    sentinel = "replace-with-" + "n" * 24
    cookie_key = "c" * 40
    cases = [
        run_unsafe(
            "placeholder-secret",
            {
                "ATLAS_ENVIRONMENT": "production",
                "ATLAS_SECRET_KEY": sentinel,
                "ATLAS_COOKIE_SECURE": "true",
                "ATLAS_CREDENTIAL_ENCRYPTION_KEYS": "prod-01=" + "k" * 40,
                "ATLAS_DATABASE_URL": "postgresql+psycopg://atlas:atlas@127.0.0.1:9/atlas",
            },
            sentinel,
            "placeholder is not allowed",
        ),
        run_unsafe(
            "insecure-cookie",
            {
                "ATLAS_ENVIRONMENT": "production",
                "ATLAS_SECRET_KEY": cookie_key,
                "ATLAS_COOKIE_SECURE": "false",
                "ATLAS_CREDENTIAL_ENCRYPTION_KEYS": "prod-01=" + "k" * 40,
                "ATLAS_DATABASE_URL": "postgresql+psycopg://atlas:atlas@127.0.0.1:9/atlas",
            },
            cookie_key,
            "ATLAS_COOKIE_SECURE must be true",
        ),
        run_unsafe(
            "deterministic-provider",
            {
                "ATLAS_ENVIRONMENT": "production",
                "ATLAS_SECRET_KEY": cookie_key,
                "ATLAS_COOKIE_SECURE": "true",
                "ATLAS_CREDENTIAL_ENCRYPTION_KEYS": "prod-01=" + "m" * 40,
                "ATLAS_LLM_PROVIDER": "double",
                "ATLAS_DATABASE_URL": "postgresql+psycopg://atlas:atlas@127.0.0.1:9/atlas",
            },
            cookie_key,
            "Deterministic providers are not allowed",
        ),
    ]
    password = secrets.token_hex(24)
    report: dict[str, object] = {"rejected": cases}
    try:
        report["ready"] = prove_ready(password)
        report["live_projects_unchanged"] = before == live_markers()
        ready = report["ready"]
        ok = (
            all(case["rejected"] is True for case in cases)
            and ready["health_status"] == "healthy"
            and ready["docs_status"] == 404
            and ready["ready_status"] == 200
            and ready["health_endpoint"] == 200
            and ready["server_user_dropped"] is True
            and ready["secret_absent_from_process_list"] is True
            and report["live_projects_unchanged"] is True
        )
        report["ok"] = ok
        RESULT.parent.mkdir(parents=True, exist_ok=True)
        RESULT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"startup_proof ok={str(ok).lower()} health={ready['health_status']}")
        return 0 if ok else 2
    except (RuntimeError, OSError, TimeoutError) as exc:
        logs = subprocess.run(
            ["docker", "logs", "--tail", "80", API],
            capture_output=True,
            text=True,
            check=False,
        )
        state = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}", API],
            capture_output=True,
            text=True,
            check=False,
        )
        detail = (logs.stdout + logs.stderr).replace(password, "[redacted]")[-700:]
        print(f"startup_failed {exc}")
        print(state.stdout.strip())
        if detail:
            print(detail)
        return 2
    finally:
        cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
