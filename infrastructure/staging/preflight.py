"""Validate staging configuration without connecting to any service."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

DEFAULT_ENV = Path(__file__).with_name(".env")
PLACEHOLDERS = ("replace-with", "dev-only", "change-me", "changeme")


def read_env(path: Path) -> dict[str, str]:
    settings = {}
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
    except ValueError:
        return False


def problems(settings: dict[str, str]) -> list[str]:
    issues = []
    get = settings.get
    if get("STAGING_ENVIRONMENT") != "production":
        issues.append("STAGING_ENVIRONMENT must be production")
    secrets = set()
    for key in ("STAGING_SECRET_KEY", "STAGING_POSTGRES_PASSWORD", "STAGING_N8N_ENCRYPTION_KEY"):
        value = get(key, "")
        if not strong(value) or value in secrets:
            issues.append(f"{key} requires a unique, randomly generated secret")
        secrets.add(value)
    key_ids: set[str] = set()
    for entry in get("STAGING_CREDENTIAL_ENCRYPTION_KEYS", "").split(","):
        key_id, _, secret = entry.partition("=")
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key_id)
            or key_id == "legacy-secret-key"
            or key_id in key_ids
            or not strong(secret.strip())
            or secret in secrets
        ):
            issues.append("STAGING_CREDENTIAL_ENCRYPTION_KEYS requires an independent keyring")
            break
        key_ids.add(key_id)
        secrets.add(secret)

    host = get("STAGING_HOST", "atlas.localhost")
    port = get("STAGING_HTTPS_PORT", "443")
    origin = f"https://{host}" if port == "443" else f"https://{host}:{port}"
    cors = {entry.strip() for entry in get("STAGING_CORS_ORIGINS", "").split(",") if entry.strip()}
    if not https_origin(origin) or origin not in cors or not all(map(https_origin, cors)):
        issues.append("STAGING_CORS_ORIGINS must include the staged HTTPS origin")

    if get("STAGING_LLM_PROVIDER", "openai") not in {"openai", "groq"} or not strong(
        get("STAGING_LLM_API_KEY", ""), 16
    ):
        issues.append("Configure staging chat provider credentials")
    embedding = get("STAGING_EMBEDDING_PROVIDER", "ollama")
    if embedding not in {"ollama", "openai"} or (
        embedding == "openai" and not strong(get("STAGING_EMBEDDING_API_KEY", ""), 16)
    ):
        issues.append("Configure staging embedding provider access")
    if get("STAGING_EMBEDDING_DIMENSIONS", "768") not in {"768", "1536"}:
        issues.append("STAGING_EMBEDDING_DIMENSIONS must be 768 or 1536")

    hook_id, hook_secret = get("STAGING_HOOK_KEY_ID", ""), get("STAGING_HOOK_SECRET", "")
    if hook_id or hook_secret:
        try:
            UUID(hook_id)
        except ValueError:
            issues.append("STAGING_HOOK_KEY_ID must be the organization webhook key UUID")
        if not strong(hook_secret, 32):
            issues.append("STAGING_HOOK_SECRET must match the active signing key")

    inbox_secret = get("STAGING_INBOX_WEBHOOK_SECRET", "")
    if inbox_secret and not strong(inbox_secret):
        issues.append("STAGING_INBOX_WEBHOOK_SECRET requires a randomly generated secret")

    calendar_settings = (
        get("STAGING_GOOGLE_CALENDAR_CLIENT_ID", ""),
        get("STAGING_GOOGLE_CALENDAR_CLIENT_SECRET", ""),
        get("STAGING_GOOGLE_CALENDAR_REDIRECT_URI", ""),
        get("STAGING_GOOGLE_CALENDAR_WEB_ORIGIN", ""),
    )
    if any(calendar_settings):
        client_id, client_secret, redirect, web_origin = calendar_settings
        if not client_id.endswith(".apps.googleusercontent.com") or not strong(client_secret, 16):
            issues.append("Configure valid Google Calendar OAuth client credentials")
        if web_origin != origin or redirect != origin + "/api/v1/calendar/google/callback":
            issues.append("Google Calendar OAuth origin and callback must match the staged HTTPS origin")

    campaign_origin = get("STAGING_CAMPAIGN_PUBLIC_URL", "")
    if campaign_origin and campaign_origin.rstrip("/") != origin:
        issues.append("STAGING_CAMPAIGN_PUBLIC_URL must match the staged HTTPS origin")
    campaign_secret = get("STAGING_CAMPAIGN_LINK_SECRET", "")
    if campaign_secret and (not strong(campaign_secret) or campaign_secret in secrets):
        issues.append("STAGING_CAMPAIGN_LINK_SECRET requires an independent signing key")

    billing = get("STAGING_BILLING_PROVIDER", "sandbox")
    if billing == "stripe":
        secret = get("STAGING_STRIPE_SECRET_KEY", "")
        if not secret.startswith(("sk_test_", "rk_test_")) or not strong(secret, 16):
            issues.append("Stripe staging requires a test-mode API key")
        signing = get("STAGING_STRIPE_WEBHOOK_SECRET", "")
        if not signing.startswith("whsec_") or not strong(signing, 16):
            issues.append("Stripe staging requires a webhook signing secret")
        try:
            prices = json.loads(get("STAGING_STRIPE_PRICE_IDS", ""))
        except ValueError:
            prices = None
        if (
            not isinstance(prices, dict)
            or not prices
            or not all(
                isinstance(value, str) and value.startswith("price_") for value in prices.values()
            )
        ):
            issues.append("STAGING_STRIPE_PRICE_IDS must map plans to test Price IDs")
        if get("STAGING_BILLING_PUBLIC_URL", "").rstrip("/") != origin:
            issues.append("STAGING_BILLING_PUBLIC_URL must match the staged HTTPS origin")
    elif billing != "sandbox":
        issues.append("STAGING_BILLING_PROVIDER must be sandbox or stripe")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    args = parser.parse_args()
    try:
        issues = problems(read_env(args.env_file))
    except (OSError, UnicodeError):
        print("Staging configuration could not be read.")
        return 2
    for issue in issues:
        print(f"Blocked: {issue}")
    if issues:
        return 2
    print(
        "Staging configuration passed local checks. Runtime, TLS, and provider checks are pending."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
