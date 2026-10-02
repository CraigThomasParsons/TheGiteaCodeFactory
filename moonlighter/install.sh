#!/usr/bin/env bash
#
# install.sh — one-shot local setup for TheNightCrew.
#
# What it does (idempotent — safe to re-run):
#   1. Installs PHP + Node dependencies.
#   2. Creates .env from .env.example if missing.
#   3. Generates the app key and Reverb credentials when they are empty.
#   4. Runs database migrations.
#   5. Registers a worker for this machine and prints its API token.
#   6. Starts the dev stack (serve + queue + reverb + vite) unless --no-serve.
#
# Usage:
#   ./install.sh                 # full setup, then start the dev server
#   ./install.sh --no-serve      # setup only (no long-running dev server)
#   WORKER_REPOS="a/b,c/d" ./install.sh   # repos this worker serves
#
set -euo pipefail

# Always operate from the repository root, wherever the script is called from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

ENV_FILE="${SCRIPT_DIR}/.env"
WORKER_ID="${WORKER_ID:-$(hostname)}"
WORKER_REPOS="${WORKER_REPOS:-owner/project}"
SERVE=1

for arg in "$@"; do
    case "${arg}" in
        --no-serve) SERVE=0 ;;
        *) echo "Unknown option: ${arg}" >&2; exit 1 ;;
    esac
done

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }

# Fail early with a clear message when a required tool is missing.
require() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 1
    fi
}

require php
require composer
require npm

# Set KEY=VALUE in .env only when KEY is currently present-but-empty. Existing
# non-empty values are never overwritten, so re-running is safe.
set_env_if_empty() {
    key="$1"
    value="$2"
    if grep -qE "^${key}=$" "${ENV_FILE}"; then
        # Use a non-/ delimiter because values may contain slashes.
        sed -i "s|^${key}=$|${key}=${value}|" "${ENV_FILE}"
    fi
}

say "Installing PHP dependencies"
composer install

say "Installing Node dependencies"
npm install

if [ ! -f "${ENV_FILE}" ]; then
    say "Creating .env from .env.example"
    cp "${SCRIPT_DIR}/.env.example" "${ENV_FILE}"
fi

# The app key is empty on a fresh .env; key:generate is itself idempotent-safe
# because we only call it when APP_KEY has no value yet.
if grep -qE "^APP_KEY=$" "${ENV_FILE}"; then
    say "Generating application key"
    php artisan key:generate
fi

say "Ensuring Reverb credentials"
# Reverb needs an id/key/secret to broadcast; generate them once if blank. php
# is already a hard requirement, so we use it for randomness (no openssl needed).
set_env_if_empty "REVERB_APP_ID" "$(php -r 'echo random_int(100000, 999999);')"
set_env_if_empty "REVERB_APP_KEY" "$(php -r 'echo bin2hex(random_bytes(16));')"
set_env_if_empty "REVERB_APP_SECRET" "$(php -r 'echo bin2hex(random_bytes(16));')"

say "Running migrations"
php artisan migrate --no-interaction

say "Registering this worker (${WORKER_ID})"
# Re-running mints a fresh token; the old one keeps working until revoked.
php artisan night-crew:worker:create "${WORKER_ID}" --repos="${WORKER_REPOS}"

if [ "${SERVE}" -eq 1 ]; then
    say "Starting the dev stack (Ctrl+C to stop)"
    composer run dev
else
    say "Setup complete. Start the dev stack with: composer run dev"
fi
