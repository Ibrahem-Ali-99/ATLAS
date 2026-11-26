"""Finish Harbor provider journeys that are still open.

Set ATLAS_HARBOR_CONNECTIONS=apply and ATLAS_HARBOR_DATABASE_URL to
atlas_harbor. `continue` runs the website, Resend feedback, n8n callback, and
WhatsApp checks. `billing` only records the subscription Stripe already
reports. Neither command prints a secret or a checkout address.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.demo.harbor_operations import continue_journeys, record_billing
from app.scripts.harbor_demonstration import assert_harbor_target


def main() -> int:
    if os.environ.get("ATLAS_HARBOR_CONNECTIONS") != "apply":
        print(
            "Set ATLAS_HARBOR_CONNECTIONS=apply to run Harbor provider journeys.",
            file=sys.stderr,
        )
        return 1
    mode = sys.argv[1] if len(sys.argv) > 1 else "continue"
    if mode not in {"continue", "billing"}:
        print("Use continue or billing.", file=sys.stderr)
        return 1
    target_url = os.environ.get("ATLAS_HARBOR_DATABASE_URL", "")
    try:
        assert_harbor_target(target_url)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    engine = create_engine(target_url, pool_pre_ping=True)
    runner = continue_journeys if mode == "continue" else record_billing
    try:
        with Session(engine) as harbor:
            steps = runner(harbor)
    except AppError as exc:
        print(json.dumps({"status": "refused", "code": exc.code, "detail": exc.message}))
        return 1
    print(json.dumps({"status": "recorded", "steps": [asdict(step) for step in steps]}, indent=2))
    print("Provider results were recorded on the Harbor agent run. No secret was printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
