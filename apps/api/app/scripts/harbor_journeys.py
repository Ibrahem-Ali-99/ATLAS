"""Finish Harbor provider journeys that are still open.

Set ATLAS_HARBOR_CONNECTIONS=apply and ATLAS_HARBOR_DATABASE_URL to
atlas_harbor. `continue` runs the website, Resend feedback, n8n callback, and
WhatsApp checks. `billing` only records the subscription Stripe already
reports. `whatsapp` confirms the stored token and does not send. `resend`
reads delivery feedback for the stored test and does not send again.
Neither command prints a secret or a checkout address.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.demo.harbor_operations import (
    accept_whatsapp,
    continue_journeys,
    record_billing,
    refresh_resend,
)
from app.scripts.harbor_demonstration import assert_harbor_target


def main() -> int:
    if os.environ.get("ATLAS_HARBOR_CONNECTIONS") != "apply":
        print(
            "Set ATLAS_HARBOR_CONNECTIONS=apply to run Harbor provider journeys.",
            file=sys.stderr,
        )
        return 1
    mode = sys.argv[1] if len(sys.argv) > 1 else "continue"
    runners = {
        "continue": continue_journeys,
        "billing": record_billing,
        "whatsapp": accept_whatsapp,
        "resend": refresh_resend,
    }
    if mode not in runners:
        print("Use continue, billing, whatsapp, or resend.", file=sys.stderr)
        return 1
    target_url = os.environ.get("ATLAS_HARBOR_DATABASE_URL", "")
    try:
        assert_harbor_target(target_url)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    engine = create_engine(target_url, pool_pre_ping=True)
    runner = runners[mode]
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
