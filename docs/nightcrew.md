# TheNightCrew integration and observed gaps

TheNightCrew is a coordinator, not an executor: durable jobs, atomic claims,
worker identity, tracker fences and a dashboard. Workers hold checkouts and run
agents. Its source ADR explicitly preserves that split. The factory adds the
end-to-end workflow and setup contract around those existing parts.

## Evidence inspected

Inspected local revision `2371e1c627f1c742416d4c6a22b140dc732242c7` on 2026-09-28:
README, CONTEXT, ADR 0001, API routes, `TransitionJobStatus.php`, ready intake docs,
and the `scripts/gitea_night` worker. The local README still says scaffolding, but
code contains intake, claims and PR stages. Documentation state is not deployment proof.
Untracked local files were left untouched; no live queue or PR was mutated.

The supplied handoff reports completion-evidence and quota fixes, a Paperclip canary,
lock staleness follow-ups and inconsistent claims about issue requeue. Treat its
PR numbers/statuses as historical, not freshly verified server state.

**Verified code finding:** the `claimed/running → queued` branch is inside
`JobKind::PullRequest`. Ordinary issue jobs use `claimed → running → done|failed`.
Do not teach clients to requeue issue jobs until the server supports it. On quota,
park/retain the claim and block a second claim pending an explicit recovery path.

## API responsibilities

All routes below are relative to the coordinator API base and authenticated with
the worker's Sanctum token, distinct from the Gitea PAT:

| Route | Purpose |
|---|---|
| GET `/worker/me` | Verify worker and allowed repositories |
| POST `/intake/gitea-ready` | Admit configured `ready-for-agent` issues idempotently |
| POST `/repos/{owner}/{repo}/jobs` | Canonical job intake |
| POST `/claim-next` | Atomic claim of eligible work |
| PATCH `/jobs/{job}/status` | Report supported transition / PR receipt and claim token |
| GET `/pr-jobs` | Discover PR-stage history |

Read the deployed server's request validators before constructing bodies. Do not
write its DB or simulate a successful claim locally. Source-key deduplication means
a repeated intake scan must not resurrect completed jobs.

## Included worker snapshot

`integrations/nightcrew/scripts/gitea-night-worker` and `gitea_night/*.py` preserve
the existing local worker, with source hashes in `provenance.json`. No Laravel server
or live configuration is copied. Install/deploy the actual TheNightCrew repository
separately using its own setup; this kit's Compose supplies only Gitea and Actions.

Inspect available flags without claiming work:

```bash
bash integrations/nightcrew/scripts/gitea-night-worker --help
```

Its stages are `discover`, `review`, `resolve`. They are **operational**, not dry-run
commands: discovery can enqueue jobs/change labels; resolution can invoke merging.
Pass `--gitea-url`, `--nightcrew-url`, `--gitea-token`, `--nightcrew-token`, `--owner`
and a private `--state-dir` explicitly. Legacy token-file defaults remain in the
snapshot for fidelity; do not depend on another user's files.

It uses `night:*` labels, `.gitea/night-merge.json` from the trusted target revision,
Claude-first execution with one Codex fallback, and fixed America/Toronto windows:
review 00:30–02:59, resolve 03:00–06:59. These are source defaults, not factory-wide
policy. Review its source/tests before changing scheduling or provider routing.
The new coach helper is not yet wired into this worker.

## Required integration work before a fleet rollout

- Prove issue completion from merged PR + acceptance evidence; exit 0 must never
  directly close an issue. The source's Done transition fences the issue closed,
  so callers must withhold Done until verified (server enforcement is desirable).
- Implement/test ordinary issue-job parking/requeue and claim-safe retry. Exit 75
  signals provider exhaustion, not a tested successful requeue.
- Standardize lease/heartbeat recovery across launcher families. The handoff shows
  AMPB, Portfolio/RTS and feudal-frontiers have different implementations; one copied
  patch is not evidence for all. Prefer kernel advisory locks for local writer life,
  while preserving coordinator claims across machines.
- Connect actual provider events to the coach and use matching runtime adapters.
- Exercise restart, lost network reply, dirty worktree, quota, stale heartbeat,
  duplicate intake and missing-acceptance cases against an isolated coordinator.
- Migrate each project to one controller; preserve existing receipts and job history.

Its discovery currently holds PRs when an outbound push mirror is configured.
Therefore add the GitHub distribution stage deliberately after cohort completion,
or implement an explicit validated policy change; automatic always-on push mirroring
would otherwise stall ongoing PR processing. See [releases](releases.md).
