"""Run the idempotent identity seed from the repository root."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.scripts.seed import main

if __name__ == "__main__":
    raise SystemExit(main())
