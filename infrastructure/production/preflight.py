"""Validate production configuration without connecting to any service."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

DEFAULT_ENV = Path(__file__).with_name(".env")
EXAMPLE_ENV = Path(__file__).with_name(".env.example")
PLACEHOLDERS = ("replace-with", "dev-only", "change-me", "changeme")
LOCAL_NAMES = {"localhost", "127.0.0.1"}
LOCAL_SMTP = {"127.0.0.1", "localhost", "mailpit", "::1"}
WEAK_PASSWORDS = {"atlas", "password", "postgres", "admin", "secret"}


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
    host = settings.get("PRODUCTION_HOST", "")
    port = settings.get("PRODUCTION_HTTPS_PORT", "443")
    if port == "443":
        return f"https://{host}"
    return f"https://{host}:{port}"


def problems(settings: dict[str, str]) -> list[str]:
    issues: list[str] = []
    get = settings.get
    if get("PRODUCTION_ENVIRONMENT") != "production":
        issues.append("PRODUCTION_ENVIRONMENT must be production")
    if get("PRODUCTION_PUBLIC_DEMO", "false").lower() == "true":
        issues.append("PRODUCTION_PUBLIC_DEMO must be false")
    if get("PRODUCTION_COOKIE_SECURE", "true").lower() != "true":
        issues.append("PRODUCTION_COOKIE_SECURE must be true")
    if get("PRODUCTION_LOG_LEVEL", "INFO").upper() == "DEBUG":
        issues.append("PRODUCTION_LOG_LEVEL must not be DEBUG")

    secrets: set[str] = set()
    for key in ("PRODUCTION_SECRET_KEY", "PRODUCTION_POSTGRES_PASSWORD", "PRODUCTION_N8N_ENCRYPTION_KEY"):
        value = get(key, "")
        if not strong(value) or value in secrets or value.lower() in WEAK_PASSWORDS:
            issues.append(f"{key} requires a unique, randomly generated secret")
        secrets.add(value)
    password = get("PRODUCTION_POSTGRES_PASSWORD", "")
    user = get("PRODUCTION_POSTGRES_USER", "atlas")
    if password and password == user:
        issues.append("PRODUCTION_POSTGRES_PASSWORD must not match the database user")
    elif not re.fullmatch(r"[A-Za-z0-9]{32,}", password) and not any(
        issue.startswith("PRODUCTION_POSTGRES_PASSWORD requires") for issue in issues
    ):
        issues.append("PRODUCTION_POSTGRES_PASSWORD must be a long alphanumeric password")

    key_ids: set[str] = set()
    for entry in get("PRODUCTION_CREDENTIAL_ENCRYPTION_KEYS", "").split(","):
        key_id, _, secret = entry.partition("=")
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key_id)
            or key_id == "legacy-secret-key"
            or key_id in key_ids
            or not strong(secret.strip())
            or secret in secrets
        ):
            issues.append("PRODUCTION_CREDENTIAL_ENCRYPTION_KEYS requires an independent keyring")
            break
        key_ids.add(key_id)
        secrets.add(secret)

    host = get("PRODUCTION_HOST", "")
    http_port = get("PRODUCTION_HTTP_PORT", "")
    https_port = get("PRODUCTION_HTTPS_PORT", "")
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host) or host.startswith(".") or ".." in host:
        issues.append("PRODUCTION_HOST must be a hostname")
    if not re.fullmatch(r"[0-9]{1,5}", http_port) or not re.fullmatch(r"[0-9]{1,5}", https_port):
        issues.append("PRODUCTION_HTTP_PORT and PRODUCTION_HTTPS_PORT must be port numbers")
    elif not local_host(host) and (http_port != "80" or https_port != "443"):
        issues.append("A public hostname must publish ports 80 and 443")
    origin = origin_for(settings)
    cors = {entry.strip() for entry in get("PRODUCTION_CORS_ORIGINS", "").split(",") if entry.strip()}
    if not https_origin(origin) or origin not in cors or not all(map(https_origin, cors)):
        issues.append("PRODUCTION_CORS_ORIGINS must include the production HTTPS origin")
    campaign = get("PRODUCTION_CAMPAIGN_PUBLIC_URL", "")
    if campaign.rstrip("/") != origin:
        issues.append("PRODUCTION_CAMPAIGN_PUBLIC_URL must match the production HTTPS origin")

    provider = get("PRODUCTION_LLM_PROVIDER", "")
    model = get("PRODUCTION_LLM_MODEL", "")
    if provider not in {"openai", "groq"} or not strong(get("PRODUCTION_LLM_API_KEY", ""), 16):
        issues.append("Configure a production chat provider")
    if not model or any(marker in model.lower() for marker in PLACEHOLDERS):
        issues.append("PRODUCTION_LLM_MODEL must name a chat model")
    if provider == "double" or get("PRODUCTION_EMBEDDING_PROVIDER", "ollama") == "double":
        issues.append("Deterministic providers are not allowed in production")
    embedding = get("PRODUCTION_EMBEDDING_PROVIDER", "ollama")
    embedding_url = get("PRODUCTION_EMBEDDING_BASE_URL", "http://ollama:11434/v1")
    if embedding not in {"ollama", "openai"}:
        issues.append("Configure production embedding provider access")
    elif embedding == "openai" and not strong(get("PRODUCTION_EMBEDDING_API_KEY", ""), 16):
        issues.append("Configure production embedding provider access")
    elif embedding == "ollama" and not _private_embedding_url(embedding_url):
        issues.append("PRODUCTION_EMBEDDING_BASE_URL must use the private Ollama service")
    if get("PRODUCTION_EMBEDDING_DIMENSIONS", "768") not in {"768", "1536"}:
        issues.append("PRODUCTION_EMBEDDING_DIMENSIONS must be 768 or 1536")

    email_mode = get("PRODUCTION_EMAIL_MODE", "sandbox")
    smtp_host = get("PRODUCTION_SMTP_HOST", "mailpit").strip().lower()
    if email_mode == "sandbox" and smtp_host not in LOCAL_SMTP:
        issues.append("Sandbox email must use the private mailbox")
    elif email_mode == "live":
        if get("PRODUCTION_EMAIL_LIVE_ENABLED", "").lower() != "true" or smtp_host in LOCAL_SMTP:
            issues.append("Live email requires an external SMTP host and the live gate")
    elif email_mode != "sandbox":
        issues.append("PRODUCTION_EMAIL_MODE must be sandbox or live")
    if get("PRODUCTION_WHATSAPP_LIVE_ENABLED", "false").lower() == "true":
        issues.append("PRODUCTION_WHATSAPP_LIVE_ENABLED must stay false until live messaging is accepted")

    _optional_secrets(settings, secrets, issues)
    _billing(settings, origin, issues)
    _calendar(settings, origin, issues)
    return issues


def _private_embedding_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return False
    return parsed.path.rstrip("/") == "/v1"


def _optional_secrets(settings: dict[str, str], secrets: set[str], issues: list[str]) -> None:
    get = settings.get
    hook_id, hook_secret = get("PRODUCTION_HOOK_KEY_ID", ""), get("PRODUCTION_HOOK_SECRET", "")
    if hook_id or hook_secret:
        try:
            UUID(hook_id)
        except ValueError:
            issues.append("PRODUCTION_HOOK_KEY_ID must be the organization webhook key UUID")
        if not strong(hook_secret, 32) or hook_secret in secrets:
            issues.append("PRODUCTION_HOOK_SECRET must match the active signing key")
    for key in (
        "PRODUCTION_INBOX_WEBHOOK_SECRET",
        "PRODUCTION_WHATSAPP_WEBHOOK_VERIFY_TOKEN",
        "PRODUCTION_WHATSAPP_WEBHOOK_APP_SECRET",
        "PRODUCTION_CAMPAIGN_LINK_SECRET",
    ):
        value = get(key, "")
        if value and (not strong(value) or value in secrets):
            issues.append(f"{key} requires an independent secret")


def _billing(settings: dict[str, str], origin: str, issues: list[str]) -> None:
    billing = settings.get("PRODUCTION_BILLING_PROVIDER", "sandbox")
    secret = settings.get("PRODUCTION_STRIPE_SECRET_KEY", "")
    if secret.startswith(("sk_live_", "rk_live_")):
        issues.append("Live Stripe keys are rejected")
        return
    if billing == "sandbox":
        return
    if billing != "stripe":
        issues.append("PRODUCTION_BILLING_PROVIDER must be sandbox or stripe")
        return
    if not secret.startswith(("sk_test_", "rk_test_")) or not strong(secret, 16):
        issues.append("Stripe production boot requires a test-mode API key")
    signing = settings.get("PRODUCTION_STRIPE_WEBHOOK_SECRET", "")
    if not signing.startswith("whsec_") or not strong(signing, 16):
        issues.append("Stripe production boot requires a webhook signing secret")
    try:
        prices = json.loads(settings.get("PRODUCTION_STRIPE_PRICE_IDS", ""))
    except ValueError:
        prices = None
    if (
        not isinstance(prices, dict)
        or not prices
        or not all(isinstance(value, str) and value.startswith("price_") for value in prices.values())
    ):
        issues.append("PRODUCTION_STRIPE_PRICE_IDS must map plans to test Price IDs")
    if settings.get("PRODUCTION_BILLING_PUBLIC_URL", "").rstrip("/") != origin:
        issues.append("PRODUCTION_BILLING_PUBLIC_URL must match the production HTTPS origin")


def _calendar(settings: dict[str, str], origin: str, issues: list[str]) -> None:
    values = (
        settings.get("PRODUCTION_GOOGLE_CALENDAR_CLIENT_ID", ""),
        settings.get("PRODUCTION_GOOGLE_CALENDAR_CLIENT_SECRET", ""),
        settings.get("PRODUCTION_GOOGLE_CALENDAR_REDIRECT_URI", ""),
        settings.get("PRODUCTION_GOOGLE_CALENDAR_WEB_ORIGIN", ""),
    )
    if not any(values):
        return
    client_id, client_secret, redirect, web_origin = values
    if not client_id.endswith(".apps.googleusercontent.com") or not strong(client_secret, 16):
        issues.append("Configure valid Google Calendar OAuth client credentials")
    if web_origin != origin or redirect != origin + "/api/v1/calendar/google/callback":
        issues.append("Google Calendar OAuth origin and callback must match the production HTTPS origin")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    args = parser.parse_args()
    try:
        issues = problems(read_env(args.env_file))
    except (OSError, UnicodeError):
        print("Production configuration could not be read.")
        return 2
    for issue in issues:
        print(f"Blocked: {issue}")
    if issues:
        return 2
    print("Production configuration passed local checks. TLS and provider checks remain external.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
