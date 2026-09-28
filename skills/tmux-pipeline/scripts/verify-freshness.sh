#!/usr/bin/env bash
# verify-freshness.sh — phase-5 gate: refuse to report verification counts whose
# evidence predates the branch tip.
#
# On 2026-08-27, PR 655's body was nearly written from BDD logs captured before
# that morning's commits; the worker noticed and said so, which is the only
# reason the numbers were caught. This script makes that catch mechanical: it
# compares each evidence file's mtime against the HEAD commit time and fails if
# any evidence is older. Stale numbers presented confidently are worse than no
# numbers.
#
# Usage: verify-freshness.sh <worktree> <evidence-file>...
#   <worktree>       the branch checkout whose HEAD defines "fresh"
#   <evidence-file>  captured logs the PR body quotes counts from
#                    (bdd-net/bdd-oracle captures, dotnet test .trx or logs, …)
#
# Exit codes: 0 all evidence is at or after the HEAD commit time
#             1 at least one file is stale (or missing) — re-run the suite
#             2 usage / infrastructure error
set -uo pipefail

wt="${1:-}"; shift || true
[ -d "$wt" ] || { echo "FATAL: worktree not found: $wt"; exit 2; }
[ "$#" -ge 1 ] || { echo "FATAL: pass at least one evidence file"; exit 2; }

head_epoch="$(git -C "$wt" log -1 --format=%ct 2>/dev/null)" || { echo "FATAL: not a git worktree: $wt"; exit 2; }
head_sha="$(git -C "$wt" rev-parse --short HEAD)"
head_human="$(git -C "$wt" log -1 --format=%ci)"

echo "HEAD $head_sha committed $head_human"
stale=0
for f in "$@"; do
  if [ ! -f "$f" ]; then
    echo "STALE  $f  (missing — no evidence at all)"
    stale=1
    continue
  fi
  m_epoch="$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f")"
  m_human="$(date -d "@$m_epoch" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -r "$m_epoch" '+%Y-%m-%d %H:%M:%S')"
  if [ "$m_epoch" -lt "$head_epoch" ]; then
    echo "STALE  $f  (captured $m_human, BEFORE HEAD)"
    stale=1
  else
    echo "FRESH  $f  (captured $m_human)"
  fi
done

if [ "$stale" -eq 1 ]; then
  echo "----"
  echo "VERDICT: STALE. Do not quote these counts in the PR body. Re-run the"
  echo "suites at HEAD $head_sha and re-capture, or state plainly in the PR"
  echo "body that the measurements predate the final commits and name the"
  echo "commit they were measured at."
  exit 1
fi
echo "----"
echo "VERDICT: FRESH. Counts from these captures describe HEAD $head_sha."
exit 0
