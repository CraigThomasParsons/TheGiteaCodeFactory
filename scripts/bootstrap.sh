#!/usr/bin/env bash
# Prepare local configuration only. Starting services is a separate command.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v docker >/dev/null
docker compose version >/dev/null
umask 077
mkdir -p secrets
if [[ ! -e .env ]]; then cp .env.example .env; fi
if [[ ! -e secrets/runner-token ]]; then : > secrets/runner-token; fi
docker compose config --quiet
printf '%s\n' 'Prepared. Follow docs/setup.md to start Gitea, finish installation and register Actions.'
