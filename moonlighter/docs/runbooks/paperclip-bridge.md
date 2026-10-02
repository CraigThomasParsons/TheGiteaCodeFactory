# Paperclip → NightCrew process bridge

`scripts/tools/paperclip_bridge.py` lets a Paperclip **process adapter** drive
night-crew work without becoming a second queue. NightCrew's atomic claim stays
the only execution ownership; Gitea stays the authority for scope and PRs. The
bridge never merges, releases or deploys. (Issue #36, outcome #35.)

## Contract

- **One bounded tick per invocation.** Paperclip runs
  `python3 scripts/tools/paperclip_bridge.py tick --config <file>` and reads the
  single JSON object printed on stdout (`status`, `job_id`, `next_retry_at`, …).
  Exit `0` = healthy outcome (including `busy`, `idle`, `waiting_provider`,
  `all_providers_unavailable`, `failed`); exit `3` = blocked/halted and needs a
  human; exit `1` = transport/config error.
- **Dispatch is opt-in.** A tick claims, reports status or launches only when
  the config sets `"dispatch_enabled": true` (the JSON boolean). Otherwise — or
  with `tick --observe` — it runs an **observation-only** tick: `GET
  /api/worker/me` and `GET /api/worker/jobs`, nothing else. No claim, no
  status PATCH, no launcher, no ledger or lock write. It prints one stable,
  sorted JSON object (`status: observed`, `observe_reason`, `registration`,
  `held_jobs`, `unknown_held_jobs`, `ledger_active_jobs`, `halt_reason`) with
  claim tokens omitted; exit `0` when registration matches, `3` otherwise.
- **No overlapping writers.** Each tick takes an exclusive `flock` on
  `<state_dir>/bridge.lock` and passes that descriptor to the launcher, so a
  still-running descendant normally keeps later ticks `busy`. The lock is not
  proof: a nested tool that closes inherited descriptors drops it while still
  running. Restart reconciliation therefore also probes the recorded launcher
  pid and its process group (via `/proc`, non-zombie members) and halts with
  `launcher_still_alive` if anything survives.
- **Host-scoped token.** The client refuses every HTTP redirect (the token
  would otherwise be replayed to the `Location` host) and ignores
  `*_proxy` environment variables.
- **Durable ledger.** `<state_dir>/ledger.json` is rewritten atomically (temp
  file, fsync, rename). A claim *intent* is written before `POST /claim-next`,
  so a lost response is adopted on the next tick via
  `GET /api/worker/jobs` instead of claiming again.
- **Registration check first.** `GET /api/worker/me` must report the configured
  `worker_id` and exactly the configured repositories, or the bridge halts.
- **Rejected work.** Contested jobs, pull-request jobs (owned by the gitea-night
  worker), unconfigured repositories and foreign ownership are recorded as
  `blocked` and never launched.
- **No idle model calls.** A launcher runs only for a job the worker already holds.

## Outcomes and states

| Launcher result | Bridge action |
| --- | --- |
| exit = provider `quota_exit_code` (default 75) or receipt `status: provider_unavailable` | `waiting_provider`; claim kept; provider cooldown persisted until receipt `retry_at` or `cooldown_seconds` |
| exit ≠ 0 otherwise | task failure → `PATCH status=failed` with evidence |
| exit 0 + valid receipt `phase: done` **and** repository `done_supported: true` | `PATCH status=done` (this closes the Gitea issue) |
| exit 0 + valid receipt `phase: done` without `done_supported` | `blocked` (`done_requires_audited_launcher`); claim kept |
| exit 0 + valid receipt `phase: ready_for_review` | claim kept, issue **not** done; Gitea review is next |
| exit 0 with no/invalid receipt | `blocked` — exit 0 alone never means done |
| launcher exits but live descendants remain in its group | halted (`launcher_descendants_alive`) |
| timeout | SIGTERM then SIGKILL to the whole group, each waiting for the group to empty; `blocked` (`launcher_timeout`). If the group cannot be proven empty, the bridge halts (`launcher_cleanup_unproven`) instead of releasing ownership |

The launcher writes its receipt to `{receipt_path}` (also `$NIGHTCREW_BRIDGE_RECEIPT`).
It must echo the attempt binding the bridge hands it
(`$NIGHTCREW_BRIDGE_ATTEMPT`, `$NIGHTCREW_BRIDGE_ATTEMPT_NONCE`,
`$NIGHTCREW_BRIDGE_REPO`, `$NIGHTCREW_BRIDGE_WORKTREE`; also template fields
`{attempt}` and `{attempt_nonce}`) and record every validation command with its
exit code:

```json
{"job_id": "42", "attempt": 1, "attempt_nonce": "<from env>", "repo": "owner/ExampleGame",
 "worktree": "/abs/path/to/worktree", "phase": "ready_for_review", "revision": "<git HEAD>",
 "validation": {"passed": true, "commands": [{"command": "php artisan test", "exit_code": 0}]}}
```

A receipt is accepted only when job, attempt, nonce, repository and worktree
match this launch, every command record exited `0`, `revision` equals the
worktree HEAD, and the worktree is clean (no unrecorded tracked or untracked
changes). The nonce is fresh per attempt, so a receipt left by an earlier
attempt can never prove a later one.

Process containment is limited to the launcher's session/process group:
launchers must not daemonize (`setsid`/double-fork) work that touches the
worktree, because the bridge cannot see or stop anything that leaves the group.

Restart reconciliation fails closed: a ledger entry left `launching`/`running`
with no receipt halts the bridge (`unexpected_process_death`); an unknown held
job without a claim intent halts (`unknown_held_job`); a job NightCrew no longer
lists is marked `lost` and never touched again. After investigating, clear with
`paperclip_bridge.py clear-halt --config <file> --note "<what you checked>"`.

## Providers

New work is claimed only when **every** served repository has an eligible
provider; otherwise the tick exits `0` with `all_providers_unavailable` (or
`providers_unavailable`) and `next_retry_at`. A waiting job resumes on the
**same** provider after its cooldown. Healthy providers keep taking other new
work meanwhile.

### Explicit handoff (never silent)

```
paperclip_bridge.py handoff --config <file> --job 42 --to codex --evidence handoff.json
```

`handoff.json` records `from_provider`, `worktree`, `revision`, `phase`,
`attempt`, `worktree_digest` and a passed `validation` with command records.
It is accepted only when the repository's launcher declares
`handoff_supported: true`, the old launcher pid and process group are gone,
and worktree/revision/phase/attempt all match the recorded checkpoint.
At a quota checkpoint the bridge records `checkpoint_digest` (a digest of
`git status`, the HEAD-relative diff and untracked file contents), so
uncommitted checkpoint work is preserved and required: `worktree_digest`
must equal it and the live worktree must still match it. Any unrecorded
dirty drift is rejected (`handoff_worktree_state_mismatch`); a same-provider
resume with drift is blocked (`worktree_changed_while_waiting`). The Feudal Frontiers launcher supports only
Claude/Codex and rejects implicit provider changes, so it is configured without
`handoff_supported`: handoffs stay blocked with an actionable reason until an
audited launcher exists.

## Known gap: `ready_for_review` is never reconciled after merge

A validated `ready_for_review` receipt keeps the NightCrew claim `running`
and the ledger entry active. The bridge has no Gitea client and no audited
evidence that the PR merged (merge commit on the target branch, required
checks, the linked issue), so it deliberately **never** transitions such a
claim itself. Consequences until a verified reconciler exists:

- each such claim occupies one `max_held_jobs` slot indefinitely;
- the job is released only when a human (or a future reconciler that
  verifies the merge) moves it on in NightCrew; the next tick then marks the
  ledger entry `lost` with reason `… after ready_for_review; outcome not
  verified by bridge` and never acts on it again.

A phase string written by an AI launcher is not merge evidence: the bridge
never reports `done` (which closes the Gitea issue) from it unless the
repository's launcher is audited and declared `done_supported: true`.

## Configuration

```json
{
  "api_base": "http://127.0.0.1:8771/api",
  "worker_id": "nas-01",
  "dispatch_enabled": false,
  "token_file": "~/.config/moonlighter/night_crew_token",
  "state_dir": "~/.local/state/paperclip-bridge",
  "timeout_seconds": 5400,
  "max_held_jobs": 3,
  "providers": {
    "codex": {"cooldown_seconds": 3600},
    "claude": {"cooldown_seconds": 3600, "quota_exit_code": 75}
  },
  "repositories": {
    "owner/ExampleGame": {
      "worktree": "/abs/path/to/worktree",
      "providers": ["codex", "claude"],
      "phase": "implement",
      "launch": {
        "codex": ["/abs/launcher", "--provider", "codex", "--issue", "{reference}", "--receipt", "{receipt_path}"],
        "claude": ["/abs/launcher", "--provider", "claude", "--issue", "{reference}", "--receipt", "{receipt_path}"]
      }
    }
  }
}
```

Set `"dispatch_enabled": true` only after an observation tick has confirmed
identity and held jobs. Optional timing keys: `terminate_grace_seconds`
(default 10, per signal) and `descendant_grace_seconds` (default 5).

Template fields: `{job_id} {repo} {reference} {kind} {provider} {worktree}
{revision} {phase} {receipt_path} {resume} {attempt} {attempt_nonce}`. The token comes from `token_file`
or `token_env`, is sent only to `api_base`'s host, is removed from the
launcher's environment, and is never printed.

## Rollback

The bridge is inert unless Paperclip is configured to invoke it. To roll back,
remove the Paperclip process-adapter command; the ledger under `state_dir` can
be archived. NightCrew claims still held stay visible via `GET /api/worker/jobs`
and on the dashboard for manual release.
