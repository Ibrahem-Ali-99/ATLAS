# ruff: noqa: E501
"""Forward Stripe test webhooks to a Harbor API and complete test checkout.

Set ATLAS_HARBOR_CONNECTIONS=apply. The operational API and its webhook secret
stay in place. This process uses the Stripe CLI signing secret only for the
Harbor API it starts. Official test card 4242 is the only payment method.
Secrets and the checkout address are not printed.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.billing.provider import create_checkout_url, price_map
from app.domains.billing.service import (
    ensure_plans,
    entitlement_plan_code,
    get_subscription,
    plan_for,
)
from app.domains.demo.harbor_operations import record_billing
from app.domains.identity.models import Organization
from app.scripts.harbor_demonstration import assert_harbor_target, database_name

_SECRET = re.compile(r"(whsec_[A-Za-z0-9]+)")
_CARD = "4242424242424242"
_PORT = 8010


def main() -> int:
    if os.environ.get("ATLAS_HARBOR_CONNECTIONS") != "apply":
        print("Set ATLAS_HARBOR_CONNECTIONS=apply to complete Harbor test checkout.", file=sys.stderr)
        return 1
    if _CARD != "4242424242424242":
        print("Only the official Stripe test card is allowed.", file=sys.stderr)
        return 1
    settings = get_settings()
    target = os.environ.get("ATLAS_HARBOR_DATABASE_URL", "")
    try:
        assert_harbor_target(target)
        if database_name(settings.database_url) == "atlas_harbor":
            raise RuntimeError("Refusing to replace the process database with Harbor.")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    cli = Path(os.environ.get("ATLAS_STRIPE_CLI", Path(os.environ["TEMP"]) / "stripe-cli" / "stripe.exe"))
    if not cli.is_file():
        print("The Stripe CLI is not available.", file=sys.stderr)
        return 1
    listen = _listen(cli, settings.stripe_secret_key)
    api: subprocess.Popen[str] | None = None
    try:
        secret = _signing_secret(listen)
        api = _api(target, secret)
        _wait_ready()
        checkout = _checkout_url(target)
        _submit(checkout)
        if not _wait_for_plan(target):
            print("checkout_submitted_webhook_missing")
            return 1
        with Session(create_engine(target)) as harbor:
            steps = record_billing(harbor)
        print("billing_recorded")
        for step in steps:
            print(f"{step.name} {step.status} {step.code or ''}".rstrip())
        return 0
    except AppError as exc:
        print(f"refused {exc.code} {_redact(exc.message)}")
        return 1
    finally:
        _stop(api)
        _stop(listen)


def _listen(cli: Path, api_key: str) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["STRIPE_API_KEY"] = api_key
    return subprocess.Popen(
        [
            str(cli),
            "listen",
            "--forward-to",
            f"http://127.0.0.1:{_PORT}/api/v1/billing/webhooks/stripe",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _signing_secret(process: subprocess.Popen[str]) -> str:
    deadline = time.time() + 30
    output = process.stdout
    if output is None:
        raise AppError(503, "stripe_listen_failed", "Stripe forwarding did not start")
    while time.time() < deadline:
        line = output.readline()
        if not line:
            if process.poll() is not None:
                break
            continue
        found = _SECRET.search(line)
        if found:
            return found.group(1)
    raise AppError(503, "stripe_listen_failed", "Stripe forwarding did not provide a signing secret")


def _api(database_url: str, secret: str) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["ATLAS_DATABASE_URL"] = database_url
    env["ATLAS_STRIPE_WEBHOOK_SECRET"] = secret
    env["ATLAS_PUBLIC_API_URL"] = f"http://127.0.0.1:{_PORT}"
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(_PORT),
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_ready() -> None:
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            response = httpx.get(f"http://127.0.0.1:{_PORT}/api/v1/health", timeout=2)
        except httpx.HTTPError:
            time.sleep(0.5)
            continue
        if response.status_code == 200:
            return
        time.sleep(0.5)
    raise AppError(503, "harbor_api_unavailable", "The Harbor API did not become ready")


def _checkout_url(database_url: str) -> str:
    engine = create_engine(database_url)
    with Session(engine) as db:
        org = db.scalar(select(Organization).where(Organization.slug == "harbor-showcase"))
        if org is None:
            raise AppError(404, "harbor_admin_missing", "The Harbor showcase organization is missing")
        ensure_plans(db)
        plan_code, interval = next(iter(price_map())).split(":", 1)
        plan_for(db, plan_code)
        row = get_subscription(db, org.id, lock=True)
        if row.provider_customer_id is None:
            raise AppError(409, "billing_customer_missing", "Harbor has no Stripe customer")
        return create_checkout_url(plan_code, interval, str(org.id), row.provider_customer_id)


def _submit(checkout: str) -> None:
    web = Path(__file__).resolve().parents[4] / "apps" / "web"
    script = Path(__file__).with_name("stripe_checkout_page.js")
    env = os.environ.copy()
    env["ATLAS_CHECKOUT_URL"] = checkout
    env["NODE_PATH"] = str(web / "node_modules")
    completed = subprocess.run(
        ["node", str(script)],
        cwd=str(web),
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        detail = _redact(completed.stderr or completed.stdout or "checkout_failed")
        found = re.search(r"error=([^ ].{0,160})", detail)
        raise AppError(502, "checkout_failed", found.group(1)[:180] if found else detail[:180])


def _wait_for_plan(database_url: str) -> bool:
    engine = create_engine(database_url)
    deadline = time.time() + 45
    while time.time() < deadline:
        with Session(engine) as db:
            org = db.scalar(select(Organization).where(Organization.slug == "harbor-showcase"))
            if org is None:
                return False
            row = get_subscription(db, org.id)
            if entitlement_plan_code(row) != "free" and row.provider_subscription_id:
                return True
        time.sleep(1)
    return False


def _redact(value: str) -> str:
    text = re.sub(r"(sk_test_|rk_test_|whsec_|https://checkout\.stripe\.com/\S+)", "[redacted]", value)
    return " ".join(text.split())


def _stop(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
