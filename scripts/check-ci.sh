#!/usr/bin/env bash
# Validation that runs anywhere, including a CI runner.
#
# Deliberately excludes anything needing the Docker CLI: the documented
# `factory-node` runner image (node:22-bookworm) has Node, Python and Git but no
# Docker, so a `docker compose` step there fails red for an environment reason
# rather than a code one. Compose validation lives in check-local.sh.
#
# This is the script a project's .gitea/workflows/pr-validation.yml should run.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m unittest discover -s tests -v
python3 -m unittest discover -s skills/pr-review-resolve-loop/tests -v
python3 -m unittest discover -s skills/slice-pipeline/scripts -p 'test_*.py' -v
node --test scripts/reviewer/tests/*.test.js
python3 -m compileall -q scripts skills moonlighter/scripts

# Syntax-only check of every shipped shell script; does not execute them.
while IFS= read -r -d '' script; do
    bash -n "$script"
done < <(find scripts skills moonlighter/scripts moonlighter/install.sh -name '*.sh' -print0)
