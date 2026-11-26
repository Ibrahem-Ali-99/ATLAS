"""Exercise real providers against the isolated Harbor showcase.

The command writes only atlas_harbor. It copies sealed grants from the
operational workspace and does not copy customers. Set
ATLAS_HARBOR_CONNECTIONS=apply to run it. Live WhatsApp, live email, live
campaigns, and a live Stripe key are refused.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.demo.harbor_operations import run
from app.scripts.harbor_demonstration import assert_harbor_target, database_name


def main() -> int:
    if os.environ.get("ATLAS_HARBOR_CONNECTIONS") != "apply":
        print(
            "Set ATLAS_HARBOR_CONNECTIONS=apply to run Harbor provider operations.",
            file=sys.stderr,
        )
        return 1
    settings = get_settings()
    source_url = settings.database_url
    target_url = os.environ.get("ATLAS_HARBOR_DATABASE_URL", "")
    try:
        if database_name(source_url) == "atlas_harbor":
            raise RuntimeError("Refusing to read grants from the Harbor database.")
        assert_harbor_target(target_url)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    source_engine = create_engine(source_url, pool_pre_ping=True)
    harbor_engine = create_engine(target_url, pool_pre_ping=True)
    try:
        with Session(source_engine) as source, Session(harbor_engine) as harbor:
            steps = run(source, harbor)
    except AppError as exc:
        print(json.dumps({"status": "refused", "code": exc.code, "detail": exc.message}))
        return 1
    print(json.dumps({"status": "recorded", "steps": [asdict(step) for step in steps]}, indent=2))
    print("Provider results were recorded on the Harbor agent run. No secret was printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
