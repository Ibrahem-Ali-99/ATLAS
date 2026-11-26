"""Write the Harbor & Co. demonstration into a database named atlas_harbor.

The command refuses every other database name, production, a public demo,
and live provider settings. It does not print a password or call a provider.
Interactive demo sessions do not use this command. They write the same
dataset into a short-lived visitor organization.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import hash_password
from app.domains.crm.models import Company
from app.domains.demo.harbor_catalog import COMPANY_COUNT
from app.domains.demo.harbor_workspace import populate
from app.domains.identity.models import Membership, MembershipRole, Organization, User

HARBOR_DATABASE = "atlas_harbor"
SHOWCASE_SLUG = "harbor-showcase"
SHOWCASE_EMAIL = "harbor-showcase@harbor.example"


def database_name(url: str) -> str:
    return urlparse(url).path.rsplit("/", 1)[-1].split("?", 1)[0]


def assert_harbor_target(url: str) -> str:
    if database_name(url) != HARBOR_DATABASE:
        raise RuntimeError(
            "Harbor demonstration provisioning only writes the atlas_harbor database."
        )
    return url


def assert_sandbox(settings: Settings) -> None:
    blocked: list[str] = []
    if settings.environment == "production":
        blocked.append("production")
    if settings.public_demo:
        blocked.append("a public demo")
    if settings.email_mode != "sandbox" or settings.email_live_enabled:
        blocked.append("live email")
    if settings.campaign_live_enabled:
        blocked.append("live campaigns")
    if settings.whatsapp_live_enabled:
        blocked.append("live WhatsApp")
    if settings.n8n_lead_webhook_url.strip():
        blocked.append("an n8n URL")
    if settings.llm_provider != "double" or settings.llm_api_key.strip():
        blocked.append("a paid chat model")
    if settings.embedding_provider != "double" or settings.embedding_api_key.strip():
        blocked.append("paid embeddings")
    if settings.billing_provider != "sandbox" or settings.stripe_secret_key.strip():
        blocked.append("a payment provider")
    if settings.google_calendar_client_secret.strip():
        blocked.append("a Google Calendar client secret")
    if blocked:
        raise RuntimeError("Harbor demonstration provisioning refuses " + ", ".join(blocked) + ".")


def assert_storage(path: Path, live: Path) -> Path:
    if not str(path).strip():
        raise RuntimeError(
            "Set ATLAS_HARBOR_STORAGE_DIR to a directory outside the active upload store."
        )
    resolved = path.expanduser().resolve()
    live_resolved = live.expanduser().resolve()
    if resolved == live_resolved or resolved.is_relative_to(live_resolved):
        raise RuntimeError("Harbor documents must use a directory outside the active upload store.")
    if live_resolved.is_relative_to(resolved):
        raise RuntimeError("Harbor documents must use a directory outside the active upload store.")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def main() -> int:
    if os.environ.get("ATLAS_HARBOR_DEMO") != "apply":
        print(
            "Set ATLAS_HARBOR_DEMO=apply to provision the isolated demonstration.",
            file=sys.stderr,
        )
        return 1
    try:
        url = assert_harbor_target(os.environ.get("ATLAS_HARBOR_DATABASE_URL", ""))
        settings = get_settings()
        assert_sandbox(settings)
        storage = assert_storage(
            Path(os.environ.get("ATLAS_HARBOR_STORAGE_DIR", "")),
            settings.upload_storage_dir,
        )
        password = os.environ.get("ATLAS_HARBOR_PASSWORD", "")
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if password and len(password) < 12:
        print("ATLAS_HARBOR_PASSWORD must be at least 12 characters.", file=sys.stderr)
        return 1
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        print(
            f"The atlas_harbor database is not reachable ({type(exc).__name__}).",
            file=sys.stderr,
        )
        return 1
    with Session(engine) as db:
        organization = _organization(db, password)
        count = db.scalar(
            select(func.count())
            .select_from(Company)
            .where(Company.organization_id == organization.id)
        )
        if int(count or 0) >= COMPANY_COUNT:
            print("Harbor demonstration records are already in atlas_harbor.")
            return 0
        if int(count or 0) > 0:
            print(
                "atlas_harbor is only partly populated. Drop that database and run this again.",
                file=sys.stderr,
            )
            return 1
        user = db.scalar(select(User).where(User.email == SHOWCASE_EMAIL))
        if user is None:
            print("The showcase account was not created.", file=sys.stderr)
            return 1
        populate(db, organization, user, storage_root=storage)
    print("Harbor demonstration records are in the atlas_harbor database.")
    print("No provider was called. No password was printed.")
    if password:
        print(f"Sign-in email: {SHOWCASE_EMAIL}")
    else:
        print("Sign-in was not enabled. Set ATLAS_HARBOR_PASSWORD to choose a password.")
    print(
        "Point a sandbox API at atlas_harbor and this storage directory before opening it."
    )
    return 0


def _organization(db: Session, password: str) -> Organization:
    organization = db.scalar(select(Organization).where(Organization.slug == SHOWCASE_SLUG))
    if organization is None:
        organization = Organization(name="Harbor & Co.", slug=SHOWCASE_SLUG)
        db.add(organization)
        db.flush()
    user = db.scalar(select(User).where(User.email == SHOWCASE_EMAIL))
    if user is None:
        user = User(
            email=SHOWCASE_EMAIL,
            full_name="Harbor showcase",
            password_hash=hash_password(password or uuid.uuid4().hex),
            is_active=bool(password),
        )
        db.add(user)
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                organization_id=organization.id,
                role=MembershipRole.admin,
            )
        )
    elif password:
        user.password_hash = hash_password(password)
        user.is_active = True
    db.commit()
    return organization


if __name__ == "__main__":
    raise SystemExit(main())
