#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s skills/pr-review-resolve-loop/tests -v
python3 -m unittest discover -s skills/slice-pipeline/scripts -p 'test_*.py' -v
node --test scripts/reviewer/tests/*.test.js
python3 -m compileall -q scripts skills moonlighter/scripts
while IFS= read -r -d '' script; do bash -n "$script"; done < <(find scripts skills moonlighter/scripts moonlighter/install.sh -name '*.sh' -print0)
docker compose --env-file .env.example --profile actions config --quiet
