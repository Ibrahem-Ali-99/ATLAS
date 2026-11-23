#!/bin/sh
# The image starts as root so a fresh named volume can be given to uid 10001.
# setpriv replaces this process, so the server is pid 1 and is not root.
# Do not leave a second copy of this process running.
set -eu

storage="${ATLAS_STORAGE_DIR:-/var/lib/atlas/storage}"
models="${ATLAS_MODEL_DIR:-/var/lib/atlas/models}"
mkdir -p "$storage" "$models"
chown -R atlas:atlas "$storage" "$models"

exec setpriv --reuid=atlas --regid=atlas --init-groups --inh-caps=-all \
    sh -c 'alembic upgrade head && exec "$@"' sh "$@"
