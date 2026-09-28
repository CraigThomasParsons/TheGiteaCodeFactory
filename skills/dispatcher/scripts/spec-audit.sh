#!/usr/bin/env bash
# spec-audit.sh — verify a slice's crosswalk (the spec) against the feature tree
# (the truth) BEFORE filing issues against it. The spec can be stale or wrong; a
# worker dispatched against a wrong spec builds the wrong thing faithfully.
#
# Example of what it catches (from a real run on a migration project's
# "14-leagues-public-pages" slice):
#   - the umbrella named a tag (@slice-14-leagues-public-pages) that exists
#     nowhere in the repo,
#   - the crosswalk header undercounted the tree by 2 files / 17 scenarios,
#   - event-inquiry-submission-review.feature was in the tag surface with ZERO
#     crosswalk coverage (which then became its own issue).
# This script makes that check a formal dispatch step instead of a lucky habit.
#
# Usage: spec-audit.sh <features-dir> <crosswalk.md> [expected-tag]...
#   <features-dir>  e.g. tests/bdd/features/14-leagues-public-pages
#   <crosswalk.md>  e.g. net/docs/plan/parity-crosswalk/14-leagues-public-pages.md
#   [expected-tag]  tags an issue/umbrella claims (e.g. @slice-14-leagues);
#                   each is verified to actually exist in the tree
#
# Exit codes: 0 spec and tree agree on everything checked
#             1 discrepancies found — fix them before filing issues
#             2 usage error
set -uo pipefail

dir="${1:-}"; xwalk="${2:-}"; shift 2 || true
[ -d "$dir" ]   || { echo "FATAL: features dir not found: $dir"; exit 2; }
[ -f "$xwalk" ] || { echo "FATAL: crosswalk not found: $xwalk"; exit 2; }

bad=0
say() { printf '%s\n' "$*"; }

# --- measure the tree --------------------------------------------------------
files=$(find "$dir" -name '*.feature' | sort)
nfiles=$(printf '%s\n' "$files" | grep -c . || true)
nscen=0
say "== tree =="
while IFS= read -r f; do
  [ -n "$f" ] || continue
  c=$(grep -cE '^[[:space:]]*(Scenario|Scenario Outline):' "$f" || true)
  nscen=$((nscen + c))
  printf '  %-50s %3d scenarios\n' "$(basename "$f")" "$c"
done <<< "$files"
say "  TOTAL: $nfiles files, $nscen scenarios"

say ""
say "== tag census (tree) =="
tags=$(grep -rhoE --include='*.feature' '@[A-Za-z0-9][A-Za-z0-9_-]*' "$dir" | sort | uniq -c | sort -rn | awk '$2 ~ /^@slice-|^@net-pending$/ {print}')
printf '%s\n' "$tags" | sed 's/^/  /'

# --- check 1: every tree file is contracted in the crosswalk -----------------
say ""
say "== check: every feature file appears in the crosswalk =="
while IFS= read -r f; do
  [ -n "$f" ] || continue
  base="$(basename "$f")"
  stem="${base%.feature}"
  if grep -qF "$stem" "$xwalk"; then
    say "  OK        $base"
  else
    say "  UNCONTRACTED  $base  ($(grep -cE '^[[:space:]]*(Scenario|Scenario Outline):' "$f") scenarios in the tag surface with no spec)"
    bad=1
  fi
done <<< "$files"

# --- check 2: claimed tags exist in the tree ---------------------------------
if [ "$#" -ge 1 ]; then
  say ""
  say "== check: claimed tags exist in the tree =="
  for t in "$@"; do
    if grep -rq --include="*.feature" -e "$t" "$dir"; then
      say "  OK        $t"
    else
      say "  MISSING   $t  (claimed by an issue or the crosswalk, absent from every feature file)"
      bad=1
    fi
  done
fi

# --- check 3: numeric claims in the crosswalk vs measured totals -------------
say ""
say "== check: crosswalk numeric claims vs measured =="
claims=$(grep -ohE '[0-9]+ (feature files|files|scenarios)' "$xwalk" | sort -u)
if [ -z "$claims" ]; then
  say "  (crosswalk states no parsable file/scenario totals)"
else
  match=0
  while IFS= read -r c; do
    n="${c%% *}"; unit="${c#* }"
    case "$unit" in
      scenarios)          [ "$n" = "$nscen" ]  && { say "  OK        claim '$c' matches measured"; match=1; } ;;
      files|"feature files") [ "$n" = "$nfiles" ] && { say "  OK        claim '$c' matches measured"; match=1; } ;;
    esac
  done <<< "$claims"
  if [ "$match" -eq 0 ]; then
    say "  MISMATCH  crosswalk claims: $(printf '%s' "$claims" | tr '\n' ';')"
    say "            measured:        $nfiles files, $nscen scenarios"
    say "            (stale proof header, or scoped to a subset - verify which)"
    bad=1
  fi
fi

say ""
if [ "$bad" -eq 1 ]; then
  say "VERDICT: SPEC DRIFT. File the gaps (uncontracted file -> its own doc-gap"
  say "issue; missing tag -> correct the umbrella; stale counts -> correct the"
  say "crosswalk header) BEFORE filing rungs. The tree is the truth; rungs port"
  say "what the tree holds, and the doc-gap issue makes the spec honest."
  exit 1
fi
say "VERDICT: spec and tree agree."
exit 0
