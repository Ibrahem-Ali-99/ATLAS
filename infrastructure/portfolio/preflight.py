"""Validate the public portfolio configuration without connecting to any service."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_ENV = Path(__file__).with_name(".env")
EXAMPLE_ENV = Path(__file__).with_name(".env.example")
PLACEHOLDERS = ("replace-with", "dev-only", "change-me", "changeme")
LOCAL_NAMES = {"localhost", "127.0.0.1"}
WEAK_PASSWORDS = {"atlas", "password", "postgres", "admin", "secret"}
FORBIDDEN_KEYS = (
    "PORTFOLIO_LLM_API_KEY",
    "PORTFOLIO_EMBEDDING_API_KEY",
    "PORTFOLIO_STRIPE_SECRET_KEY",
    "PORTFOLIO_STRIPE_WEBHOOK_SECRET",
    "PORTFOLIO_GOOGLE_CALENDAR_CLIENT_SECRET",
    "PORTFOLIO_WHATSAPP_WEBHOOK_APP_SECRET",
    "PORTFOLIO_N8N_LEAD_WEBHOOK_URL",
)


def read_env(path: Path) -> dict[str, str]:
    settings: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        key, delimiter, value = line.strip().partition("=")
        if delimiter and not key.startswith("#"):
            value = value.strip()
            if len(value) > 1 and value[0] in "'\"" and value[-1] == value[0]:
                value = value[1:-1]
            settings[key.strip()] = value
    return settings


def strong(secret: str, length: int = 32) -> bool:
    return len(secret) >= length and not any(marker in secret.lower() for marker in PLACEHOLDERS)


def https_origin(value: str) -> bool:
    try:
        origin = urlsplit(value)
    except ValueError:
        return False
    return (
        origin.scheme == "https"
        and bool(origin.hostname)
        and not origin.username
        and not origin.password
        and not origin.path
        and not origin.query
        and not origin.fragment
        and (origin.port is None or 0 < origin.port <= 65535)
    )


def local_host(host: str) -> bool:
    return host in LOCAL_NAMES or host.endswith(".localhost")


def origin_for(settings: dict[str, str]) -> str:
    host = settings.get("PORTFOLIO_HOST", "")
    port = settings.get("PORTFOLIO_HTTPS_PORT", "443")
    if port == "443":
        return f"https://{host}"
    return f"https://{host}:{port}"


def problems(settings: dict[str, str]) -> list[str]:
    issues: list[str] = []
    get = settings.get
    if get("PORTFOLIO_ENVIRONMENT") != "development":
        issues.append(
            "PORTFOLIO_ENVIRONMENT must be development because visitor retrieval still uses the deterministic embedding provider"
        )
    if get("PORTFOLIO_PUBLIC_DEMO", "").lower() != "true":
        issues.append("PORTFOLIO_PUBLIC_DEMO must be true")
    if get("PORTFOLIO_COOKIE_SECURE", "true").lower() != "true":
        issues.append("PORTFOLIO_COOKIE_SECURE must be true")
    if get("PORTFOLIO_LOG_LEVEL", "INFO").upper() == "DEBUG":
        issues.append("PORTFOLIO_LOG_LEVEL must not be DEBUG")
    if get("PORTFOLIO_POSTGRES_DB", "") != "atlas_portfolio":
        issues.append("PORTFOLIO_POSTGRES_DB must be atlas_portfolio")

    secrets: set[str] = set()
    for key in ("PORTFOLIO_SECRET_KEY", "PORTFOLIO_POSTGRES_PASSWORD"):
        value = get(key, "")
        if not strong(value) or value in secrets or value.lower() in WEAK_PASSWORDS:
            issues.append(f"{key} requires a unique, randomly generated secret")
        secrets.add(value)
    password = get("PORTFOLIO_POSTGRES_PASSWORD", "")
    user = get("PORTFOLIO_POSTGRES_USER", "atlas")
    if password and password == user:
        issues.append("PORTFOLIO_POSTGRES_PASSWORD must not match the database user")
    elif not re.fullmatch(r"[A-Za-z0-9]{32,}", password) and not any(
        issue.startswith("PORTFOLIO_POSTGRES_PASSWORD requires") for issue in issues
    ):
        issues.append("PORTFOLIO_POSTGRES_PASSWORD must be a long alphanumeric password")

    key_ids: set[str] = set()
    for entry in get("PORTFOLIO_CREDENTIAL_ENCRYPTION_KEYS", "").split(","):
        key_id, _, secret = entry.partition("=")
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key_id)
            or key_id == "legacy-secret-key"
            or key_id in key_ids
            or not strong(secret.strip())
            or secret in secrets
        ):
            issues.append("PORTFOLIO_CREDENTIAL_ENCRYPTION_KEYS requires an independent keyring")
            break
        key_ids.add(key_id)
        secrets.add(secret)

    host = get("PORTFOLIO_HOST", "")
    http_port = get("PORTFOLIO_HTTP_PORT", "")
    https_port = get("PORTFOLIO_HTTPS_PORT", "")
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host) or host.startswith(".") or ".." in host:
        issues.append("PORTFOLIO_HOST must be a hostname")
    if not re.fullmatch(r"[0-9]{1,5}", http_port) or not re.fullmatch(r"[0-9]{1,5}", https_port):
        issues.append("PORTFOLIO_HTTP_PORT and PORTFOLIO_HTTPS_PORT must be port numbers")
    elif not local_host(host) and (http_port != "80" or https_port != "443"):
        issues.append("A public hostname must publish ports 80 and 443")
    origin = origin_for(settings)
    cors = {entry.strip() for entry in get("PORTFOLIO_CORS_ORIGINS", "").split(",") if entry.strip()}
    if not https_origin(origin) or origin not in cors or not all(map(https_origin, cors)):
        issues.append("PORTFOLIO_CORS_ORIGINS must include the portfolio HTTPS origin")
    campaign = get("PORTFOLIO_CAMPAIGN_PUBLIC_URL", "")
    if campaign.rstrip("/") != origin:
        issues.append("PORTFOLIO_CAMPAIGN_PUBLIC_URL must match the portfolio HTTPS origin")

    for key in FORBIDDEN_KEYS:
        if get(key, "").strip():
            issues.append(f"{key} must stay empty on the public demo")
    for key, value in settings.items():
        lowered = value.lower()
        if "sk_live_" in lowered or "rk_live_" in lowered:
            issues.append("Live Stripe keys are rejected")
            break
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    args = parser.parse_args()
    try:
        issues = problems(read_env(args.env_file))
    except (OSError, UnicodeError):
        print("Portfolio configuration could not be read.")
        return 2
    for issue in issues:
        print(f"Blocked: {issue}")
    if issues:
        return 2
    print("Portfolio configuration passed local checks. TLS remains external.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
