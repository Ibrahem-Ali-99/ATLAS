#!/bin/sh
# Start the public portfolio stack after the configuration gate passes.
# Does not attach to the development, staging, or production project.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
cd "$root"
python3 infrastructure/portfolio/preflight.py --env-file infrastructure/portfolio/.env
python3 infrastructure/portfolio/compose_contract.py
exec docker compose \
  --project-name atlas-portfolio \
  -f infrastructure/compose.portfolio.yaml \
  --env-file infrastructure/portfolio/.env \
  up -d --build
