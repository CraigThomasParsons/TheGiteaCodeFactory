#!/usr/bin/env bash
# Validation that needs tooling a CI runner may not have.
#
# Currently only the Compose config parse, which requires the Docker CLI and the
# compose plugin. Kept out of check-ci.sh so the CI gate never fails for a missing
# runtime; run this on a workstation, or on a runner whose image ships Docker.
#
# A missing Docker CLI fails this script, so a passing check.sh always means the
# Compose config was parsed. Set CHECK_SKIP_COMPOSE=1 to skip it deliberately.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "${CHECK_SKIP_COMPOSE:-0}" == "1" ]]; then
    echo "check-local: CHECK_SKIP_COMPOSE=1; Compose validation skipped." >&2
    exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "check-local: docker not found; Compose config was not validated." >&2
    echo "check-local: install the Docker CLI, or set CHECK_SKIP_COMPOSE=1 to skip deliberately." >&2
    exit 1
fi

docker compose --env-file .env.example --profile actions config --quiet
