# The coordinator (Moonlighter)

The factory needs one service that owns the job queue across all worker
computers and knows which repositories are enrolled. That service is
**Moonlighter**, a Laravel application in [moonlighter/](../moonlighter/): durable
jobs, atomic claims, worker identity, tracker fences, a PR labeller that feeds the
review loops, and a live dashboard. Its code still uses its original name,
TheNightCrew.

Setup and repository registration are in [moonlighter/README.md](../moonlighter/README.md).
This page explains how it fits the factory, the rules any replacement must keep,
and its known gaps.

If you run a single worker computer, you can defer the coordinator: the tmux
pipeline's local branch/worktree locks already keep one writer per branch on one
machine. You need a coordinator once more than one computer can pick up work.

## Design rule: coordinator, not executor

The coordinator decides *who works what*; it never runs agents or holds
checkouts. Workers pull a job, execute it locally and report back. Keep that
split in any replacement: a queue that also runs work cannot safely hand a job to
another machine when the first one stalls.

## Behaviors to preserve

Each of these is easy to break when changing Moonlighter or writing a
replacement.

- **Job kinds have different lifecycles.** In Moonlighter, only pull-request jobs
  can go from `claimed`/`running` back to `queued`. Ordinary issue jobs go
  `claimed → running → done|failed` with no requeue. So when a worker hits a quota
  limit on an issue job, it must park and keep the claim rather than release it,
  until the server supports an explicit recovery path.
- **Intake is idempotent.** Jobs are deduplicated by a source key, so rescanning
  Gitea for `ready-for-agent` issues must not resurrect completed jobs.
- **Done closes the issue.** Marking a job done fences the Gitea issue closed, so a
  worker must only report done after verifying merged code and acceptance evidence.

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

The request and response bodies the worker sends are visible in
[moonlighter/scripts/gitea_night/coordinator.py](../moonlighter/scripts/gitea_night/coordinator.py);
a replacement server must accept the same shapes. Workers never write the coordinator's database directly or
simulate a successful claim locally.

## Review vocabulary

Moonlighter's PR labeller and the factory's review skills share one vocabulary:
`review:clear` for a clean review and `gitea-codex-review:v1` /
`gitea-codex-resolve:v1` comment markers naming the reviewed commit. The labeller
also accepts the older `review:clean` and `pulse-review:v1` / `pulse-resolve:v1`,
so review workers written before the change keep working. Details are in
[moonlighter/README.md](../moonlighter/README.md#review-labels-and-markers).

## The worker client

`moonlighter/scripts/gitea-night-worker` and `gitea_night/*.py` are the client
each worker computer runs. The factory's Compose supplies only Gitea and Actions;
run Moonlighter itself as described in its README.

Inspect available flags without claiming work:

```bash
bash moonlighter/scripts/gitea-night-worker --help
```

Its stages are `discover`, `review`, `resolve`. They are **operational**, not dry-run
commands: discovery can enqueue jobs/change labels; resolution can invoke merging.
Pass `--gitea-url`, `--nightcrew-url`, `--gitea-token`, `--nightcrew-token`, `--owner`
and a private `--state-dir` explicitly; don't rely on the default token paths.

It uses `night:*` labels, `.gitea/night-merge.json` from the trusted target revision,
Claude-first execution with one Codex fallback, and fixed overnight windows in the
fixed timezone America/Toronto: review 00:30–02:59, resolve 03:00–06:59. These
are source defaults, not factory-wide policy; adjust them for your hours. Review
its source and tests before changing scheduling or provider routing. The coach
helper is not yet wired into this worker.

## Known gaps before a multi-computer rollout


- Prove issue completion from merged PR + acceptance evidence; exit 0 must never
  directly close an issue. The source's Done transition fences the issue closed,
  so callers must withhold Done until verified (server enforcement is desirable).
- Implement/test ordinary issue-job parking/requeue and claim-safe retry. Exit 75
  signals provider exhaustion, not a tested successful requeue.
- Standardize lease/heartbeat recovery across worker implementations. Different
  launchers can use different lock and heartbeat mechanisms; a fix proven in one
  is not evidence for another. Prefer
  kernel advisory locks for local writer life, while preserving coordinator claims
  across machines.
- Connect actual provider events to the coach and use matching runtime adapters.
- Exercise restart, lost network reply, dirty worktree, quota, stale heartbeat,
  duplicate intake and missing-acceptance cases against an isolated coordinator.
- Migrate each project to one controller; preserve existing receipts and job history.

Its discovery currently holds PRs when an outbound push mirror is configured.
Therefore add the GitHub distribution stage deliberately after cohort completion,
or implement an explicit validated policy change; automatic always-on push mirroring
would otherwise stall ongoing PR processing. See [releases](releases.md).
