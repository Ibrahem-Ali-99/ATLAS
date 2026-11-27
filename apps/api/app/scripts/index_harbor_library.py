"""Index the Harbor enterprise library through the knowledge pipeline.

Writes only the atlas_harbor database and the Harbor storage directory.
Each file is stored and then ingested by the same worker the API runs,
which chunks the text and embeds it with the workspace embedding provider.
A file already stored with the same digest is left in place.
The command does not send a message, charge a card, or print a secret.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.demo.harbor_library import library_documents
from app.domains.identity.models import Membership, MembershipRole, Organization, User
from app.domains.knowledge.models import Document, DocumentStatus
from app.domains.knowledge.service import replace_document, store_upload
from app.domains.knowledge.worker import run_once
from app.domains.provenance.origin import Origin
from app.scripts.harbor_demonstration import HARBOR_DATABASE, assert_harbor_target, database_name


def main() -> int:
    settings = get_settings()
    url = settings.database_url
    try:
        assert_harbor_target(url)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if database_name(url) != HARBOR_DATABASE:
        print("Refusing to index a database other than atlas_harbor.", file=sys.stderr)
        return 1
    if settings.environment == "production" or settings.public_demo:
        print("Refusing to index Harbor knowledge in this environment.", file=sys.stderr)
        return 1
    configured = settings.storage_dir.strip()
    storage = Path(configured).expanduser().resolve() if configured else None
    expected_raw = os.environ.get("ATLAS_HARBOR_STORAGE_DIR", "").strip()
    expected = Path(expected_raw).expanduser().resolve() if expected_raw else None
    if storage is None or expected is None:
        print("Set ATLAS_STORAGE_DIR and ATLAS_HARBOR_STORAGE_DIR.", file=sys.stderr)
        return 1
    if storage != expected:
        print("Refusing to write outside the Harbor storage directory.", file=sys.stderr)
        return 1
    if not storage.exists():
        print("The Harbor storage directory does not exist.", file=sys.stderr)
        return 1

    engine = create_engine(url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with factory() as db:
        organization, user = _harbor(db)
        queued = _store_library(db, organization, user)
    print("organization", organization.slug)
    print("embedding_provider", settings.embedding_provider)
    print("embedding_model", settings.embedding_model)
    print("queued", queued)
    print("library_documents", len(library_documents()))
    deadline = time.monotonic() + 20 * 60
    while time.monotonic() < deadline:
        moved = run_once()
        with factory() as db:
            pending = _pending(db, organization.id)
        print("pending", len(pending), "worker_moved", int(moved))
        if not pending:
            break
        if not moved:
            time.sleep(1)
    with factory() as db:
        ready, failed = _results(db, organization.id)
    print("ready", ready)
    print("failed", failed)
    if failed or ready < len(library_documents()):
        return 1
    print("Harbor library indexed. No message was sent.")
    return 0


def _harbor(db: Session) -> tuple[Organization, User]:
    organization = db.scalar(select(Organization).where(Organization.slug == "harbor-showcase"))
    if organization is None:
        raise SystemExit("Harbor library indexing is blocked: harbor-showcase is not stored")
    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == organization.id,
            Membership.role == MembershipRole.admin,
        )
    )
    if membership is None:
        raise SystemExit("Harbor library indexing is blocked: Harbor has no administrator")
    user = db.get(User, membership.user_id)
    if user is None:
        raise SystemExit("Harbor library indexing is blocked: the Harbor administrator is missing")
    return organization, user


def _store_library(db: Session, organization: Organization, user: User) -> int:
    queued = 0
    for title, filename, body in library_documents():
        payload = body.encode()
        existing = db.scalar(
            select(Document).where(
                Document.organization_id == organization.id,
                Document.filename == filename,
                Document.archived_at.is_(None),
            )
        )
        try:
            if existing is None:
                document = store_upload(
                    db,
                    organization.id,
                    user.id,
                    filename=filename,
                    media_type="text/plain",
                    payload=payload,
                    origin=Origin.demo,
                )
                queued += 1
            else:
                document = replace_document(
                    db,
                    organization.id,
                    existing.id,
                    filename=filename,
                    media_type="text/plain",
                    payload=payload,
                )
                if document.status == DocumentStatus.pending:
                    queued += 1
        except AppError as exc:
            if exc.code != "duplicate_document":
                raise
            document = existing if existing is not None else _by_name(db, organization.id, filename)
        if document is not None and document.title != title:
            document.title = title[:200]
            db.commit()
    return queued


def _by_name(db: Session, organization_id: object, filename: str) -> Document | None:
    return db.scalar(
        select(Document).where(
            Document.organization_id == organization_id,
            Document.filename == filename,
            Document.archived_at.is_(None),
        )
    )


def _pending(db: Session, organization_id: object) -> list[str]:
    names = {filename for _title, filename, _body in library_documents()}
    rows = db.scalars(
        select(Document).where(
            Document.organization_id == organization_id,
            Document.filename.in_(names),
            Document.archived_at.is_(None),
        )
    ).all()
    return [
        row.filename
        for row in rows
        if row.status in {DocumentStatus.pending, DocumentStatus.processing}
    ]


def _results(db: Session, organization_id: object) -> tuple[int, int]:
    names = {filename for _title, filename, _body in library_documents()}
    rows = db.scalars(
        select(Document).where(
            Document.organization_id == organization_id,
            Document.filename.in_(names),
            Document.archived_at.is_(None),
        )
    ).all()
    ready = sum(1 for row in rows if row.status == DocumentStatus.ready)
    failed = sum(1 for row in rows if row.status == DocumentStatus.failed)
    return ready, failed


if __name__ == "__main__":
    raise SystemExit(main())
