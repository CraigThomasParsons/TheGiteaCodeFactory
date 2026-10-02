#!/usr/bin/env bash
# sync-moonlighter.sh — refresh moonlighter/ from a private TheNightCrew checkout.
#
# Moonlighter is developed in a private repository and published here. This
# script copies the committed files at a given revision, removes private-only
# material, rewrites personal defaults to generic ones, keeps the files this
# repository maintains itself, and refuses to finish if anything personal is
# left. Review `git diff moonlighter/` before committing.
#
# Usage: scripts/sync-moonlighter.sh <upstream-checkout> [revision]
#   MOONLIGHTER_SYNC_RULES=<file> overrides the private rules file location.
#
# Exit codes: 0 synced and clean
#             1 a leak pattern survived the rewrite rules (nothing was copied)
#             2 usage error or missing rules file
set -euo pipefail

upstream="${1:-}"
revision="${2:-HEAD}"
if [[ -z "$upstream" ]] || ! git -C "$upstream" rev-parse --git-dir >/dev/null 2>&1; then
    echo "usage: $0 <upstream-checkout> [revision]" >&2
    exit 2
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
destination="$root/moonlighter"
staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT

# Files maintained in this repository for public readers; a sync never replaces them.
owned=(
    README.md
    CLAUDE.md
    CONTEXT.md
    .env.example
    docs/adr/0001-central-coordinator-not-an-executor-or-native-queue.md
)

# Paths that exist only for the private deployment.
private_paths=(
    docs/plans
)

# Rewrite rules and the leak pattern are private: they name the details being
# removed. They live outside the repository (see
# templates/moonlighter-sync-rules.example.sh) and define:
#   rewrite_rules  sed -E expressions applied to every copied text file, in order
#   leak_pattern   an extended regex; any match after rewriting blocks the sync
rules_file="${MOONLIGHTER_SYNC_RULES:-${XDG_CONFIG_HOME:-$HOME/.config}/moonlighter-sync/rules.sh}"
if [[ ! -f "$rules_file" ]]; then
    echo "Missing rules file: $rules_file (copy templates/moonlighter-sync-rules.example.sh)" >&2
    exit 2
fi
rewrite_rules=()
leak_pattern=''
# shellcheck source=/dev/null
source "$rules_file"
# Generic leaks are always checked, whatever the private rules say.
leak_pattern="${leak_pattern:+$leak_pattern|}192\.168\.|/home/[a-z]"

git -C "$upstream" archive "$revision" | tar -x -C "$staging"
source_commit="$(git -C "$upstream" rev-parse "$revision")"

for path in "${private_paths[@]}"; do
    rm -rf "${staging:?}/$path"
done

for path in "${owned[@]}"; do
    if [[ -e "$destination/$path" ]]; then
        mkdir -p "$staging/$(dirname "$path")"
        cp "$destination/$path" "$staging/$path"
    fi
done

sed_args=()
for rule in "${rewrite_rules[@]}"; do
    sed_args+=(-e "$rule")
done
grep -rlIZ --exclude=composer.lock --exclude=package-lock.json '' "$staging" \
    | xargs -0 -r sed -i -E "${sed_args[@]}"

if grep -rnIE --exclude=composer.lock --exclude=package-lock.json "$leak_pattern" "$staging"; then
    echo "Leak check failed: the lines above still contain private details." >&2
    echo "Add a rewrite rule or mark the file as owned, then rerun." >&2
    exit 1
fi

printf 'TheNightCrew %s\n' "$source_commit" > "$staging/UPSTREAM"

# Mirror into place. Files ignored by moonlighter/.gitignore (vendor, node_modules,
# .env, built assets, runtime storage) are left untouched.
rsync -a --delete --filter=':- .gitignore' "$staging/" "$destination/"
echo "Synced moonlighter/ from TheNightCrew $source_commit"
