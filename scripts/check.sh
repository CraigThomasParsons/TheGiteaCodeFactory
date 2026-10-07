#!/usr/bin/env bash
# Full local validation: everything CI runs, plus the checks that need Docker.
#
# CI should invoke check-ci.sh directly rather than this script, because the
# documented factory-node runner image has no Docker CLI. See
# docs/setup.md.
set -euo pipefail
here="$(dirname "$0")"

bash "$here/check-ci.sh"
bash "$here/check-local.sh"
