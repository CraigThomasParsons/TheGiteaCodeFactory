#!/usr/bin/env bash
# Validation that needs tooling a CI runner may not have.
#
# Currently only the Compose config parse, which requires the Docker CLI and the
# compose plugin. Kept out of check-ci.sh so the CI gate never fails for a missing
# runtime; run this on a workstation, or on a runner whose image ships Docker.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
    echo "check-local: docker not found; skipping Compose validation." >&2
    echo "check-local: run this where the Docker CLI is available." >&2
    exit 0
fi

docker compose --env-file .env.example --profile actions config --quiet
