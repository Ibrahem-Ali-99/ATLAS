#!/bin/sh
# Pull the reviewed branch and rebuild the public portfolio stack.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
cd "$root"
git pull --ff-only
exec sh infrastructure/portfolio/up.sh
