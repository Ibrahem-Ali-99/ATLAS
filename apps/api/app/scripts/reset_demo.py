"""Clear demo activity for Atlas Demo.

This does not reset passwords and does not touch other organizations.
It runs only for a development process, with ATLAS_DEMO_RESET=yes, and only
when the database name is one of the local names this project uses.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.agents.models import AgentEvent, AgentRun
from app.domains.approvals.models import Approval
from app.domains.automation.models import (
    CalendarBooking,
    EmailMessage,
    ExecutionAttempt,
    ExecutionIntent,
    WorkflowRun,
)
from app.domains.identity.models import Organization
from app.domains.knowledge.models import Chunk, Document
from app.domains.observability.models import EvaluationRun, OperationTrace

_ALLOWED_DATABASES = frozenset({"atlas", "atlas_demo", "atlas_e2e", "atlas_test"})


def database_name(url: str) -> str:
    parsed = urlparse(url.replace("postgresql+psycopg", "postgresql", 1))
    return parsed.path.rsplit("/", 1)[-1]


def assert_reset_allowed(url: str) -> str:
    settings = get_settings()
    name = database_name(url)
    if settings.environment != "development":
        raise RuntimeError("Demo reset is allowed only when ATLAS_ENVIRONMENT=development.")
    if settings.public_demo:
        raise RuntimeError("Demo reset is refused for a public demo.")
    if os.environ.get("ATLAS_DEMO_RESET") != "yes":
        raise RuntimeError("Set ATLAS_DEMO_RESET=yes to clear demo activity.")
    if name not in _ALLOWED_DATABASES:
        raise RuntimeError("Demo reset is refused for this database name.")
    return name


def reset_demo_activity(db: Session, organization_id: object) -> None:
    """Delete stored activity for one organization. CRM rows and users stay."""

    for model in (
        CalendarBooking,
        EmailMessage,
        ExecutionAttempt,
        ExecutionIntent,
        WorkflowRun,
        Approval,
        AgentEvent,
        AgentRun,
        OperationTrace,
        EvaluationRun,
        Chunk,
        Document,
    ):
        db.execute(delete(model).where(model.organization_id == organization_id))
    db.commit()


def main() -> int:
    from app.core.database import SessionLocal

    settings = get_settings()
    try:
        assert_reset_allowed(settings.database_url)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    db = SessionLocal()
    try:
        organization = db.scalar(select(Organization).where(Organization.slug == "atlas-demo"))
        if organization is None:
            print("No atlas-demo organization is present. Nothing was deleted.")
            return 0
        reset_demo_activity(db, organization.id)
    finally:
        db.close()
    print("Cleared demo activity. Passwords and CRM records were not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
