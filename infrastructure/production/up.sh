#!/bin/sh
# Start the production stack after the configuration gate passes.
# Does not attach to the development project or atlas-staging.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
cd "$root"
python3 infrastructure/production/preflight.py --env-file infrastructure/production/.env
python3 infrastructure/production/compose_contract.py
exec docker compose \
  --project-name atlas-production \
  --project-directory infrastructure \
  -f infrastructure/compose.production.yaml \
  --env-file infrastructure/production/.env \
  up -d --build
