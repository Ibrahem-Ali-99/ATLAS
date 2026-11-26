"""Create or reuse the six ATLAS Stripe test prices.

The test key is read from ATLAS_STRIPE_SECRET_KEY in the process environment.
The command prints the price map and never prints the key. Pass --write-env to
update only the billing lines in the repository .env file.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import stripe

from app.core.errors import AppError
from app.domains.billing.test_catalog import ensure_test_catalog

_BILLING_KEYS = (
    "ATLAS_BILLING_PROVIDER",
    "ATLAS_STRIPE_SECRET_KEY",
    "ATLAS_STRIPE_WEBHOOK_SECRET",
    "ATLAS_STRIPE_PRICE_IDS",
    "ATLAS_BILLING_PUBLIC_URL",
)


def billing_environment(
    secret_key: str, price_ids: dict[str, str], public_url: str, webhook_secret: str
) -> dict[str, str]:
    return {
        "ATLAS_BILLING_PROVIDER": "stripe",
        "ATLAS_STRIPE_SECRET_KEY": secret_key,
        "ATLAS_STRIPE_WEBHOOK_SECRET": webhook_secret,
        "ATLAS_STRIPE_PRICE_IDS": json.dumps(price_ids, separators=(",", ":")),
        "ATLAS_BILLING_PUBLIC_URL": public_url,
    }


def write_billing_env(path: Path, updates: dict[str, str]) -> None:
    """Replace billing settings and keep every other line."""

    unknown = set(updates) - set(_BILLING_KEYS)
    if unknown:
        raise AppError(500, "billing_provider_error", "Refusing to write an unrelated setting")
    original = path.read_text(encoding="utf-8") if path.is_file() else ""
    newline = "\r\n" if "\r\n" in original else "\n"
    lines = original.splitlines()
    seen: set[str] = set()
    rewritten: list[str] = []
    for line in lines:
        name, separator, _value = line.partition("=")
        if separator and name in updates:
            rewritten.append(f"{name}={updates[name]}")
            seen.add(name)
        else:
            rewritten.append(line)
    missing = [key for key in _BILLING_KEYS if key in updates and key not in seen]
    if missing and rewritten and rewritten[-1] != "":
        rewritten.append("")
    rewritten.extend(f"{key}={updates[key]}" for key in missing)
    path.write_text(newline.join(rewritten) + (newline if rewritten else ""), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    secret = os.environ.get("ATLAS_STRIPE_SECRET_KEY", "")
    if not secret.startswith(("sk_test_", "rk_test_")):
        print("stripe_test_prices_refused reason=test_key_required", file=sys.stderr)
        return 2
    client = stripe.StripeClient(
        secret,
        http_client=stripe.RequestsClient(timeout=10),
        max_network_retries=1,
    )
    try:
        price_ids = ensure_test_catalog(client.v1)
    except (AppError, stripe.StripeError):
        print(f"stripe_test_prices_failed error={sys.exc_info()[0].__name__}", file=sys.stderr)
        return 1
    print(json.dumps(price_ids, separators=(",", ":")))
    if "--write-env" not in args:
        return 0
    repo_root = Path(__file__).resolve().parents[4]
    env_path = repo_root / ".env"
    public_url = os.environ.get("ATLAS_BILLING_PUBLIC_URL", "http://127.0.0.1:3000")
    webhook_secret = os.environ.get("ATLAS_STRIPE_WEBHOOK_SECRET", "")
    updates = billing_environment(secret, price_ids, public_url, webhook_secret)
    if not webhook_secret:
        del updates["ATLAS_STRIPE_WEBHOOK_SECRET"]
    write_billing_env(env_path, updates)
    print("stripe_test_prices_env_updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
