# Moonlighter — Claude Code context

Moonlighter (called TheNightCrew in its code and config) is the central
night-shift **coordinator**: a DB-backed job board + Livewire dashboard + Reverb
live feed + API that decides *who works what* across multiple computers. It
does **not** execute agent work — each Worker runs its own client locally. Read
these first:

- [`CONTEXT.md`](CONTEXT.md) — the glossary (Worker, Job, Claim, Fence, Intake…).
- [`docs/adr/0001-central-coordinator-not-an-executor-or-native-queue.md`](docs/adr/0001-central-coordinator-not-an-executor-or-native-queue.md)
  — why coordinator-not-executor, and why a custom `night_crew_jobs` table.

## Stack

Laravel 13 · PHP 8.4 · Livewire 3 · Reverb · Sanctum (per-Worker API tokens) ·
PHPUnit. Native Laravel queues are reserved for TheNightCrew's **own** internal
async only — domain Jobs live in the custom `night_crew_jobs` table, never the
framework `jobs` table.

## Non-negotiable invariants

- **Branching:** follow the containing repository's branch rules; never commit
  directly to its default or integration branch. Prefixes:
  `feature/ fix/ docs/ checkpoint/ spike/`.
- **PHP style:** `declare(strict_types=1)` on every file (Pint enforces it). The
  null-coalescing `??` and the Elvis `?:` are **forbidden**; ternaries `?:` are
  also banned in JS/TS. No single-letter variables. PHPDoc `@param`/`@return`
  required. Run `vendor/bin/pint --dirty --format agent` after **every** PHP edit.
- **Architecture:** controller methods stay thin; business logic lives in
  services/actions injected via the constructor (never `app()->make()` or `new`
  in a method body); no raw SQL (Eloquent / query builder only); no hardcoded
  credentials.
- **Comments:** JSDoc/PHPDoc on every function; inline comments explain *why*.
- **Testing:** every change is programmatically tested. A feature is "done" only
  when the relevant tests are green.
- **Secrets — never commit:** `.env`, `.env.testing`, `*.key`, `id_rsa`, `*.pem`.
  Run before every commit:

  ```bash
  git diff --cached --name-only | \
    grep -Ei '(\.env|cookies\.txt|\.key$|gitea_token|id_rsa|\.pem$)' || echo "clean"
  ```

## Syncing

This folder is refreshed from a private upstream by
`../scripts/sync-moonlighter.sh`. Edit this file, `README.md`, `CONTEXT.md`,
`.env.example` and the ADR here; change everything else upstream and sync, or
the next sync will overwrite it.
