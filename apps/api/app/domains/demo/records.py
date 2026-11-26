"""Fictional Harbor & Co. rows for one visitor organization.

The dataset is marked demo where the table has an origin. Visitor-created
documents and assistant replies are counted separately from these rows.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.domains.demo.harbor_workspace import populate
from app.domains.identity.models import Organization, User


def populate_visitor(
    db: Session,
    organization: Organization,
    user: User,
    *,
    storage_root: Path | None = None,
) -> None:
    populate(db, organization, user, storage_root=storage_root)
