# Moonlighter

Moonlighter is the factory's **coordinator**: the service that knows which
repositories are enrolled, which jobs are waiting, and which worker computer is
working on what. Your agents moonlight on your repositories while you sleep;
Moonlighter makes sure no two of them work on the same thing.

It is a job board with a live dashboard and an API. It decides *who works
what* across one or more computers, but never runs the work itself. Each
computer (a **worker**) runs a small client that pulls a job, does it locally
and reports back.

> Coordinator, not executor, and not Laravel's native queue. See
> [ADR 0001](docs/adr/0001-central-coordinator-not-an-executor-or-native-queue.md).

Its code and configuration still use its original name, **TheNightCrew**
(`NIGHT_CREW_*` settings, `nightcrew:*` commands, the `night_crew_jobs` table).
The vocabulary is defined in [CONTEXT.md](CONTEXT.md).

## What it does for the factory

| Piece | Role |
|---|---|
| **Repository registration** | Decides which Gitea repositories the factory works on (below). |
| **PR labeller** | Sweeps open PRs in registered repositories and applies the first `review:*` label, for its own worker stages. These labels are not interchangeable with the standalone factory loop (see Known gaps). |
| **Ready-issue intake** | Scans registered repositories for issues labelled `ready-for-agent` and turns each into a job, safely repeatable (the same issue never becomes two jobs). |
| **Job board** (`night_crew_jobs`) | Durable, claimable work: one-time *issue* jobs, recurring *maintenance* jobs, and *pull request* stages pinned to exact commits. |
| **Atomic claim** | The single source of truth for which worker holds which job, across machines. |
| **Fence** | Mirrors a claim onto the Gitea issue (assignee, status label, comment) so humans can see it. |
| **Schedule windows** | Weekly hours (plus one-off overrides) when workers may claim new work. |
| **Dashboard** | A Livewire board of the queue, updating live through Reverb. |
| **Worker client** ([scripts/](scripts/)) | The Python client each worker computer runs: discovers PRs, claims jobs, runs the review and resolve stages. |
| **Paperclip bridge** ([scripts/tools/paperclip_bridge.py](scripts/tools/paperclip_bridge.py)) | Lets a Paperclip process adapter run claimed jobs without becoming a second queue. Dispatch is off unless enabled; see the [runbook](docs/runbooks/paperclip-bridge.md). |

## Registering repositories

There are three lists, each answering a different question:

| Setting | Question it answers | Default |
|---|---|---|
| `NIGHT_CREW_PR_REPOS` | Which repositories' PRs get labelled for the review/resolve loops? | `*`: every non-archived repository the Gitea token can see |
| `NIGHT_CREW_READY_REPOSITORIES` | Which repositories are scanned for `ready-for-agent` issues? | none |
| `--repos` on each worker | Which repositories can *this* computer actually work on? | set when the worker is created |

A worker is only ever handed jobs for repositories it declared. To enroll a new
repository:

1. Add it to `NIGHT_CREW_READY_REPOSITORIES` in `.env` if agents should pick up
   its issues. Leave `NIGHT_CREW_PR_REPOS` at `*` or add it there.
2. Register (or re-register) each worker computer that has a checkout of it:

   ```bash
   php artisan night-crew:worker:create "$(hostname)" --repos=owner/project,owner/other
   ```

   This prints the worker's API token once; store it privately on that computer.
3. Check what the PR pipeline will touch, then do a dry run of the labeller:

   ```bash
   php artisan nightcrew:list-pr-repos
   php artisan nightcrew:label-prs --dry-run
   ```

4. Follow the factory's [onboarding guide](../docs/onboarding.md) for the
   repository side: `.factory/project.json`, workflows, labels, branch protection.

## Install

Requires PHP 8.4, Composer, Node 22 and SQLite.

```bash
cd moonlighter
./install.sh              # deps, .env, key, Reverb creds, migrate, register this worker, start dev
./install.sh --no-serve   # the same setup without starting the dev server
WORKER_REPOS="owner/project" ./install.sh --no-serve
```

Choose **one** installation command above. Re-running the installer preserves
nonempty settings but mints a new worker token; old tokens remain valid until
revoked. Store the printed token privately and revoke unused tokens.

For setup without a running dashboard, choose `./install.sh --no-serve` above.
The installer generates the application key and Reverb credentials. Then edit
`.env` to set `NIGHT_CREW_GITEA_URL`, the bot token and explicit repository
allowlists. From `moonlighter/`, start the development services with:

```bash
composer run dev
```

These are development services; configure persistent process supervision and a
web server before using this as an unattended deployment.

Use a dedicated Gitea bot account for `NIGHT_CREW_GITEA_TOKEN` and
`NIGHT_CREW_GITEA_BOT`, so crew-held and human-held issues are distinguishable.

## Running the worker client

The worker client lives in [scripts/](scripts/). Its stages are `discover`,
`review` and `resolve`. They are real operations, not dry runs: discovery can
enqueue jobs and change labels, and resolution can merge. Pass every
connection setting explicitly:

```bash
bash scripts/gitea-night-worker --help
```

[config/systemd/](config/systemd/) has example units and timers that run the
review stage from 00:30 and the resolve stage from 03:00. Edit the paths,
environment file and timezone for your machine before installing them.

## Tests

```bash
npm ci && npm run build        # the dashboard tests need the built assets
php artisan test               # 135 tests
python3 -m pytest tests/Python # 90 worker client and bridge tests
```

## Review labels and markers

The PR labeller uses the factory's vocabulary, and still accepts the older one so
existing review workers keep working:

| Meaning | Factory name | Also accepted (older workers) |
|---|---|---|
| Review found nothing to fix | `review:clear` | `review:clean` |
| Comment marker naming the reviewed commit | `gitea-codex-review:v1`, `gitea-codex-resolve:v1` | `pulse-review:v1`, `pulse-resolve:v1` |

It also uses `review:automerge`, which it grants only to crew scaffold work
(scripts, docs, Markdown) that already has a clear review. The newest marker on a
PR wins, whichever family it comes from.

## Known gaps

- **Timezone is fixed to America/Toronto** in schedule windows and the worker's
  operating window.
- Issue jobs can't yet be requeued after a quota failure, and "done" does not
  yet require merged-code evidence. See the factory's
  [coordinator notes](../docs/moonlighter.md) and [roadmap](../docs/roadmap.md).

You can install and inspect this bundled copy without access to any other
repository. The server and Python client use the older `nightcrew` identifiers
shown above for compatibility; do not substitute `moonlighter` in CLI commands.

## Where this copy comes from

Moonlighter is developed in the author's private TheNightCrew repository and
copied here with [`scripts/sync-moonlighter.sh`](../scripts/sync-moonlighter.sh),
which removes private-only material and checks for leaks. `UPSTREAM` records the
source commit of the last sync. Files this README, `CLAUDE.md`, `CONTEXT.md`,
`.env.example` and the ADR are maintained here and are not overwritten by a sync.

The private upstream is a maintainer import source, not an installation prerequisite.
Public users should work from the code included here and report suggested changes
through this repository's issues or pull requests. Maintainers must reconcile any
accepted code changes with the import process so a later sync does not overwrite them.
