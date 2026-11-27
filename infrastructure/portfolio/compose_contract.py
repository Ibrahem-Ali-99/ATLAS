"""Check the portfolio Compose file without starting containers."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

COMPOSE_FILE = Path(__file__).resolve().parents[1] / "compose.portfolio.yaml"
CADDY_FILE = Path(__file__).resolve().parents[1] / "caddy" / "Caddyfile"
REQUIRED_SERVICES = ("caddy", "web", "api", "postgres", "mailpit")
ABSENT_SERVICES = ("n8n", "embedding-model", "ollama", "chat-model")
HEALTHCHECKED = REQUIRED_SERVICES
LIMITED = {
    "caddy": "64M",
    "web": "384M",
    "api": "768M",
    "postgres": "512M",
    "mailpit": "64M",
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


def problems(text: str, caddy: str) -> list[str]:
    issues: list[str] = []
    blocks = service_blocks(text)
    missing = [name for name in REQUIRED_SERVICES if name not in blocks]
    if missing:
        issues.append("missing services: " + ", ".join(missing))
    present = [name for name in ABSENT_SERVICES if name in blocks]
    if present:
        issues.append("portfolio stack must not run " + ", ".join(present))
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
        if "healthcheck:" not in blocks.get(name, ""):
            issues.append(f"{name} has no health check")
    api = blocks.get("api", "")
    if "postgres:\n        condition: service_healthy" not in api:
        issues.append("api is missing dependency postgres")
    if "mailpit:\n        condition: service_healthy" not in api:
        issues.append("api is missing dependency mailpit")
    if "postgres/init" in text:
        issues.append("portfolio Postgres must not create development databases")
    if "POSTGRES_DB: atlas_portfolio" not in text or "/atlas_portfolio" not in text:
        issues.append("the database name must be atlas_portfolio")
    required_lines = (
        "ATLAS_ENVIRONMENT: development",
        'ATLAS_PUBLIC_DEMO: "true"',
        'ATLAS_COOKIE_SECURE: "true"',
        "ATLAS_LLM_PROVIDER: double",
        "ATLAS_LLM_BASE_URL: http://double.invalid/v1",
        "ATLAS_LLM_MODEL: double",
        'ATLAS_LLM_API_KEY: ""',
        "ATLAS_PUBLIC_INFERENCE_ENABLED: ${PORTFOLIO_PUBLIC_INFERENCE_ENABLED:-false}",
        "ATLAS_PUBLIC_LLM_AUTHORIZED: ${PORTFOLIO_PUBLIC_LLM_AUTHORIZED:-false}",
        "ATLAS_PUBLIC_LLM_MODEL: openai/gpt-oss-20b",
        "ATLAS_PUBLIC_LLM_BASE_URL: https://api.groq.com/openai/v1",
        "ATLAS_PUBLIC_LLM_API_KEY: ${PORTFOLIO_PUBLIC_LLM_API_KEY:-}",
        "context: ../apps/web-rebuild",
        "ATLAS_EMBEDDING_PROVIDER: double",
        'ATLAS_EMBEDDING_API_KEY: ""',
        "ATLAS_EMAIL_MODE: sandbox",
        'ATLAS_EMAIL_LIVE_ENABLED: "false"',
        'ATLAS_BILLING_PROVIDER: sandbox',
        'ATLAS_STRIPE_SECRET_KEY: ""',
        'ATLAS_WHATSAPP_LIVE_ENABLED: "false"',
        'ATLAS_N8N_LEAD_WEBHOOK_URL: ""',
        'ATLAS_GOOGLE_CALENDAR_CLIENT_SECRET: ""',
        "ATLAS_SMTP_HOST: mailpit",
        "ATLAS_PUBLIC_API_URL: http://api:8000",
        'ATLAS_LOGIN_EMAIL_LIMIT: "5"',
        'ATLAS_LLM_MAX_OUTPUT_TOKENS: "256"',
        'ATLAS_MAX_UPLOAD_BYTES: "2097152"',
        "ATLAS_STORAGE_DIR: /var/lib/atlas/portfolio-docs",
    )
    for line in required_lines:
        if line not in text:
            issues.append(f"portfolio Compose is missing {line}")
    if "pgvector/pgvector:pg17" not in text:
        issues.append("Postgres must be the pgvector image")
    if 'max-size: "10m"' not in text or 'max-file: "5"' not in text:
        issues.append("container logs are not limited to five 10 MB files")
    if 'respond "Not found" 404' not in caddy or "/openapi.json" not in caddy:
        issues.append("Caddy must hide the API schema on the public origin")
    if "reverse_proxy api:8000" not in caddy or "reverse_proxy web:3000" not in caddy:
        issues.append("Caddy must send /api to the API and other paths to the web app")
    if re.search(r"(?m)^      context: \.\./apps/web$", text):
        issues.append("the web image must not build the previous frontend")
    if "ollama" in text or "llama3.2" in text:
        issues.append("portfolio Compose must not run a local generation model")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", type=Path, default=COMPOSE_FILE)
    args = parser.parse_args()
    try:
        issues = problems(args.compose_file.read_text(encoding="utf-8"), CADDY_FILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        print("Portfolio Compose file could not be read.")
        return 2
    for issue in issues:
        print(f"Blocked: {issue}")
    if issues:
        return 2
    print("Portfolio Compose contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
