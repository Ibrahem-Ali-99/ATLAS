"""Print the stored Harbor review state. Does not call a provider.

Set ATLAS_HARBOR_DATABASE_URL to atlas_harbor. The command reads subscription,
integration verification, and execution rows already stored there.
"""

from __future__ import annotations

import json
import os
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.domains.billing.service import entitlement_plan_code, get_subscription
from app.domains.demo.harbor_providers import HARBOR_SLUG
from app.domains.identity.models import Organization
from app.domains.integrations.models import IntegrationConfig
from app.domains.integrations.resend_test import test_status
from app.scripts.harbor_demonstration import assert_harbor_target


def main() -> int:
    target = os.environ.get("ATLAS_HARBOR_DATABASE_URL", "")
    try:
        assert_harbor_target(target)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    with Session(create_engine(target)) as db:
        print(json.dumps(_summary(db), indent=2))
    print("Stored Harbor state only. No provider was called.")
    return 0


def _summary(db: Session) -> dict[str, object]:
    org = db.scalar(select(Organization).where(Organization.slug == HARBOR_SLUG))
    if org is None:
        return {"organization": None}
    subscription = get_subscription(db, org.id)
    integrations = []
    for row in db.scalars(
        select(IntegrationConfig)
        .where(IntegrationConfig.organization_id == org.id)
        .order_by(IntegrationConfig.integration_type)
    ):
        integrations.append(
            {
                "type": row.integration_type.value,
                "status": row.status.value,
                "verified": row.verified_at is not None,
                "detail": (row.verification_detail or "")[:180],
            }
        )
    resend = test_status(db, org.id)
    return {
        "organization": HARBOR_SLUG,
        "plan": entitlement_plan_code(subscription),
        "subscription_status": subscription.status.value,
        "provider_subscription": bool(subscription.provider_subscription_id),
        "integrations": integrations,
        "resend_acceptance": resend.provider_confirmation,
        "resend_last_event": resend.provider_last_event,
    }


if __name__ == "__main__":
    raise SystemExit(main())
