"""Check the portfolio demonstration against the product it describes.

Run from apps/api:

    python -m app.scripts.verify_portfolio_demonstration

The process reads the demonstration document, the public-site copy, and the
portfolio guards. It does not connect to a database, send a message, call
Stripe, or create a file.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from app.domains.billing.service import PLAN_DEFINITIONS
from app.domains.billing.test_catalog import TEST_PRICES
from app.scripts.portfolio_demo import (
    KNOWLEDGE_NAME,
    PORTFOLIO_DATABASE,
    VISIT_SUBJECT,
    assert_portfolio_storage,
    assert_portfolio_target,
    assert_sandbox,
)

ROOT = Path(__file__).resolve().parents[4]
DOCUMENT = ROOT / "docs" / "portfolio-demonstration.md"
PUBLIC_CATALOG = ROOT / "apps" / "web" / "src" / "lib" / "public-catalog.ts"
PUBLIC_SITE = ROOT / "apps" / "web" / "src" / "lib" / "public-site.ts"
PUBLIC_DEMO = ROOT / "apps" / "web" / "src" / "app" / "(public)" / "demo" / "page.tsx"
PUBLIC_HOME = ROOT / "apps" / "web" / "src" / "components" / "public" / "home-screen.tsx"
PUBLIC_FOOTER = ROOT / "apps" / "web" / "src" / "components" / "public" / "site-footer.tsx"
BILLING_SCREEN = ROOT / "apps" / "web" / "src" / "components" / "screens" / "billing-screen.tsx"
PORTFOLIO_COMMAND = ROOT / "apps" / "api" / "app" / "scripts" / "portfolio_demo.py"
KNOWLEDGE_SERVICE = ROOT / "apps" / "api" / "app" / "domains" / "knowledge" / "service.py"
WORKFLOW_ROUTE = ROOT / "apps" / "api" / "app" / "api" / "v1" / "workflow_definitions.py"
WORKFLOW_PANEL = (
    ROOT / "apps" / "web" / "src" / "components" / "workflows" / "workflow-run-panel.tsx"
)

REQUIRED_HEADINGS = (
    "## What is real, and what is a sandbox",
    "## Shared scene",
    "## Demonstration 1 — Intelligent customer operations",
    "## Demonstration 2 — Intelligent knowledge retrieval",
    "## Demonstration 3 — Business process automation",
    "## Demonstration 4 — SaaS engineering",
    "## 90-second product script",
    "## Five-minute technical walkthrough",
    "## Screenshot and recording shot list",
    "## Engineering claims that this pack will stand behind",
)

SHARED_NAMES = (
    "Harbor & Co.",
    "Mina Patel",
    "Northwind",
    "Lumen Freight",
    "north pier",
    "bonded",
)

BILLING_PHRASES = (
    "Stripe test mode",
    "Sandbox billing",
    "does not create a live charge",
    "Limits in effect",
    "Continue to checkout",
)


def main() -> int:
    failures: list[str] = []
    document = _read(DOCUMENT, failures)
    if document is None:
        return _finish(failures)
    _require_headings(document, failures)
    _require_scene(document, failures)
    _require_public_alignment(document, failures)
    _require_billing_copy(document, failures)
    _require_plan_numbers(document, failures)
    _require_catalog_agreement(failures)
    _require_portfolio_guards(failures)
    _require_prepared_scene(document, failures)
    _require_product_behavior(document, failures)
    _require_document_stays_offline(document, failures)
    return _finish(failures)


def _read(path: Path, failures: list[str]) -> str | None:
    if not path.is_file():
        failures.append(f"Missing {path.relative_to(ROOT)}")
        return None
    return path.read_text(encoding="utf-8")


def _require_headings(document: str, failures: list[str]) -> None:
    for heading in REQUIRED_HEADINGS:
        if heading not in document:
            failures.append(f"Document is missing heading: {heading}")


def _require_scene(document: str, failures: list[str]) -> None:
    for name in SHARED_NAMES:
        if name not in document:
            failures.append(f"Document is missing the shared name {name!r}")
    for label, value in (
        ("knowledge file", KNOWLEDGE_NAME),
        ("inquiry subject", VISIT_SUBJECT),
        ("portfolio database", PORTFOLIO_DATABASE),
    ):
        if value not in document:
            failures.append(f"Document is missing the {label} {value!r}")
    for phrase in (
        "Preview only",
        "Thursday afternoon",
        "2027-03-18",
        "Qualified lead follow-up",
        "Send the bonded service sheet",
        "Ask Mina for the missing yard details",
        "Not claimed",
        "python -m app.scripts.portfolio_demo",
        "ATLAS_PORTFOLIO_DEMO=apply",
    ):
        if phrase not in document:
            failures.append(f"Document is missing {phrase!r}")


def _require_public_alignment(document: str, failures: list[str]) -> None:
    pages = {
        "public site": _read(PUBLIC_SITE, failures),
        "public demo": _read(PUBLIC_DEMO, failures),
        "public home": _read(PUBLIC_HOME, failures),
        "public footer": _read(PUBLIC_FOOTER, failures),
    }
    if any(text is None for text in pages.values()):
        return
    site = pages["public site"] or ""
    footer = pages["public footer"] or ""
    for name in ("Harbor & Co.", "Mina Patel", "Northwind", "bonded"):
        present = [label for label, text in pages.items() if text and name in text]
        if name not in document or not present:
            failures.append(f"{name} is not shared by the document and the public pages")
    if "fictional" not in footer.casefold():
        failures.append("The public footer no longer says the companies are fictional")
    if "Staff cannot approve" not in site:
        failures.append("The public site no longer says staff cannot approve")
    if "cannot approve" not in document.casefold():
        failures.append("The document no longer says staff cannot approve")


def _require_billing_copy(document: str, failures: list[str]) -> None:
    screen = _read(BILLING_SCREEN, failures)
    if screen is None:
        return
    for phrase in BILLING_PHRASES:
        if phrase not in screen:
            failures.append(f"Billing screen is missing {phrase!r}")
        if phrase not in document:
            failures.append(f"Document is missing the billing phrase {phrase!r}")


def _require_plan_numbers(document: str, failures: list[str]) -> None:
    expected = {
        "free": (2, 100, 1_000_000_000, 2),
        "starter": (5, 1_000, 10_000_000_000, 10),
        "pro": (20, 5_000, 100_000_000_000, 50),
        "business": (100, 25_000, 1_000_000_000_000, 200),
    }
    for code, numbers in expected.items():
        definition = PLAN_DEFINITIONS[code]
        actual = (
            definition["seats"],
            definition["ai_requests"],
            definition["knowledge_storage_bytes"],
            definition["active_workflows"],
        )
        if actual != numbers:
            failures.append(f"Plan {code} no longer matches the demonstration numbers {numbers}")
    for phrase in (
        "2 seats, 100 assistant requests, 1 GB of knowledge files, and 2 active workflows",
        "5 seats, 1,000 assistant requests, 10 GB, and 10 active workflows",
        "Starter $19 or $190, Pro $49 or $490, and Business $99 or $990",
    ):
        if phrase not in document:
            failures.append(f"Document is missing the catalog sentence {phrase!r}")


def _require_catalog_agreement(failures: list[str]) -> None:
    catalog = _read(PUBLIC_CATALOG, failures)
    if catalog is None:
        return
    prices = {(price.plan_code, price.interval): price.unit_amount for price in TEST_PRICES}
    for code in ("starter", "pro", "business"):
        monthly = _catalog_cents(catalog, code, "monthlyCents")
        yearly = _catalog_cents(catalog, code, "yearlyCents")
        if monthly != prices.get((code, "monthly")):
            failures.append(f"Public monthly price for {code} does not match the test catalog")
        if yearly != prices.get((code, "yearly")):
            failures.append(f"Public yearly price for {code} does not match the test catalog")
        definition = PLAN_DEFINITIONS[code]
        rendered = f"assistantRequests: {definition['ai_requests']:,}".replace(",", "_")
        plain = f"assistantRequests: {definition['ai_requests']}"
        if rendered not in catalog and plain not in catalog:
            failures.append(f"Public catalog assistant limit for {code} drifted from the API")


def _catalog_cents(catalog: str, code: str, field: str) -> int | None:
    block = re.search(rf'code: "{code}"[\s\S]*?yearlyCents: [^,\n]+', catalog)
    if block is None:
        return None
    match = re.search(rf"{field}: ([0-9_]+|null)", block.group(0))
    if match is None or match.group(1) == "null":
        return None
    return int(match.group(1).replace("_", ""))


def _require_portfolio_guards(failures: list[str]) -> None:
    allowed = assert_portfolio_target(f"postgresql://127.0.0.1:5434/{PORTFOLIO_DATABASE}")
    if not allowed.endswith(f"/{PORTFOLIO_DATABASE}"):
        failures.append("The portfolio guard did not accept atlas_portfolio")
    for name in ("atlas", "atlas_test", "postgres", "atlas_portfolio_backup"):
        try:
            assert_portfolio_target(f"postgresql://127.0.0.1:5434/{name}")
        except RuntimeError:
            continue
        failures.append(f"The portfolio guard accepted the database {name}")
    try:
        assert_sandbox(_sandbox_settings())
    except RuntimeError as exc:
        failures.append(f"A sandbox configuration was refused: {exc}")
    for label, settings in _blocked_settings():
        try:
            assert_sandbox(settings)
        except RuntimeError:
            continue
        failures.append(f"The portfolio guard accepted {label}")
    live = ROOT / "var" / "uploads"
    try:
        assert_portfolio_storage(live, live)
    except RuntimeError:
        stored_outside = False
    else:
        stored_outside = True
    if stored_outside:
        failures.append("The portfolio guard accepted the active upload directory")


def _sandbox_settings() -> SimpleNamespace:
    return SimpleNamespace(
        environment="development",
        public_demo=False,
        email_mode="sandbox",
        email_live_enabled=False,
        campaign_live_enabled=False,
        whatsapp_live_enabled=False,
        n8n_lead_webhook_url="",
        llm_provider="double",
        llm_api_key="",
        embedding_provider="double",
        embedding_api_key="",
        billing_provider="sandbox",
        stripe_secret_key="",
        google_calendar_client_secret="",
    )


def _blocked_settings() -> tuple[tuple[str, SimpleNamespace], ...]:
    base = _sandbox_settings()
    cases = (
        ("production", {"environment": "production"}),
        ("a public demo", {"public_demo": True}),
        ("live email", {"email_mode": "live", "email_live_enabled": True}),
        ("live campaigns", {"campaign_live_enabled": True}),
        ("live WhatsApp", {"whatsapp_live_enabled": True}),
        ("an n8n URL", {"n8n_lead_webhook_url": "http://127.0.0.1:5678/webhook"}),
        ("a paid chat model", {"llm_provider": "groq", "llm_api_key": "present"}),
        ("paid embeddings", {"embedding_provider": "ollama", "embedding_api_key": ""}),
        ("a payment provider", {"billing_provider": "stripe", "stripe_secret_key": "present"}),
        ("a Google Calendar client secret", {"google_calendar_client_secret": "present"}),
    )
    built: list[tuple[str, SimpleNamespace]] = []
    for label, changes in cases:
        values = vars(base).copy()
        values.update(changes)
        built.append((label, SimpleNamespace(**values)))
    return tuple(built)


def _require_prepared_scene(document: str, failures: list[str]) -> None:
    command = _read(PORTFOLIO_COMMAND, failures)
    if command is None:
        return
    for phrase in (
        'title="Bonded warehousing overview"',
        '"title": "Send the service sheet"',
        '"otherwise_actions": []',
        'status=DocumentStatus.pending',
        '"provider": "simulation"',
        'name="Q3 cold-storage briefing"',
    ):
        if phrase not in command:
            failures.append(f"Portfolio command no longer contains {phrase}")
    for phrase in (
        "Bonded warehousing overview",
        "Send the service sheet",
        "otherwise path is empty",
        "starts pending",
        "provider `simulation`",
        "Q3 cold-storage briefing",
        "Prepare the yard agenda",
        "does not contain a fabricated citation",
    ):
        if phrase not in document:
            failures.append(f"Document no longer describes the prepared scene: {phrase}")


def _require_product_behavior(document: str, failures: list[str]) -> None:
    knowledge = _read(KNOWLEDGE_SERVICE, failures)
    route = _read(WORKFLOW_ROUTE, failures)
    panel = _read(WORKFLOW_PANEL, failures)
    if knowledge and "delete(Chunk).where(Chunk.document_id == document.id)" not in knowledge:
        failures.append("Knowledge replacement no longer deletes the old passages")
    if route and "workflow_effect_already_recorded" not in route:
        failures.append("A repeated workflow effect is no longer refused")
    if panel and "No task, lead change, or follow-up draft was saved." not in panel:
        failures.append("Workflow preview no longer says that nothing was saved")
    if "old passages" not in document.casefold() and "old passage" not in document.casefold():
        failures.append("Document no longer says replacement removes the old passages")


def _require_document_stays_offline(document: str, failures: list[str]) -> None:
    lowered = document.casefold()
    for secret in ("sk_live_", "sk_test_", "whsec_", "seed_admin_password"):
        if secret in lowered:
            failures.append(f"Document contains a secret-shaped value {secret}")
    if "restart the api" in lowered and "do not restart the api" not in lowered:
        failures.append("Document tells the operator to restart the API")


def _finish(failures: list[str]) -> int:
    if failures:
        print("Portfolio demonstration check failed:")
        for item in failures:
            print(f"- {item}")
        return 1
    print("Portfolio demonstration check passed.")
    print("No database was opened and no provider was called.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
