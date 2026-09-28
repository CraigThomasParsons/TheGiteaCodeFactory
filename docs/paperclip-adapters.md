# Paperclip adapters: observed behaviour

Companion to [coach.md](coach.md), which records that the coach never worked and that
no Paperclip settings were changed while preparing this kit. This page records a
Paperclip instance actually being installed and exercised on a host, on 2026-09-26.
It is evidence from one host, not a supported integration.

Everything below was observed directly. Where a claim is inference it says so.

## Paperclip does not route around rate limits

Checked against the documentation site (all pages, 2026-09-26): there is **no
provider rate-limit backoff and no automatic failover to another agent**. Provider
limits are disclaimed as out of scope ("those limits are Anthropic's, not
Paperclip's"). The recovery machinery is explicit that it will not reassign:

> Recovery preserves the original assignee and only retries it when that's safe.
> It doesn't take over or reassign the stranded work by itself.

Its "execution policy" is review/approval staging after work completes, not dispatch
routing. So the bench-and-hand-off behaviour `coach.md` requires is not something
Paperclip provides and is later configured; it is absent, and remains this kit's job.

## A failed run reports success

**This is the finding that matters most for a controller.** `coach.md` item 1 already
asks for JSON-envelope failure detection even when the outer CLI exits 0. Two observed
cases confirm the concern, both ending `Status: succeeded`:

| Observed failure | Run status | Work actually done |
|---|---|---|
| `HTTP 404: models/auto is not found` | `succeeded` | 1 message, 0 tool calls |
| `HTTP 429 RESOURCE_EXHAUSTED` (provider quota) | `succeeded` | 27 messages, 26 tool calls |

The adapter subprocess exits 0, so Paperclip records success. The second row is a real
provider quota refusal — precisely the event the coach must bench an account on — and
Paperclip's own status reports it as a completed run.

A controller must therefore **never treat Paperclip run status as the rate-limit
signal**. Observed usable signals, in the run log rather than the status field:

- a `Final error` line carrying the provider's own message and HTTP code
- the message/tool-call counts (a "succeeded" run that did no tool calls is suspect)
- for Hermes specifically, a `Session:`/`Duration:`/`Messages:` summary block

Distinguishing 429 (bench the account) from 404 (misconfiguration, benching will not
help) requires parsing that provider message. Benching on any `Final error` would
bench accounts for configuration faults, which `coach.md` item 5 correctly separates.

## `adapterConfig.model`, and the `models/auto` failure

The Hermes adapter reference states there is no `model` field in the adapter config,
and the adapters API reports `modelsCount: 0` for `hermes_local`. Both are misleading.

With no model configured, Paperclip passes the literal string `auto` as the model, and
the runtime forwards it to the provider, producing `404: models/auto is not found`.
Setting the agent's top-level `model` field does not help — it is silently ignored and
stays null. Setting **`adapterConfig.model`** does stick and does fix it.

This was not the runtime's fault: `hermes chat -q "..." --provider auto` succeeds
standalone, and `--provider` and `-m` are separate flags there.

Inference, untested: adapters reporting `modelsCount: 0` are the ones exposed to this,
because adapters with a real model list appear to resolve a default. `hermes_local` and
`pi_local` report 0.

Related: `agent update` **merges** `adapterConfig` rather than replacing it. Omitting a
key does not remove it; the key returns to its default.

## Adapter verification on one host

Installed CLI present for 7 of 16 registered adapters. Exercised:

| Adapter | Result |
|---|---|
| `hermes_local` | Works. One heartbeat ran 26 tool calls in 1m19s before the provider 429. |
| `grok_local` | Works. Correct protocol-aware reply reporting an empty inbox. |
| `cursor` | Fails before invoking the model: `a value is required for '--single <PROMPT>'`. Appears to be an adapter/CLI version mismatch. |
| `codex_local`, `gemini_local`, `opencode_local`, `claude_local` | Not exercised (quota exhausted, or deferred — see below). |

## Hazard: adapter skill sync deletes from the destination directory

Relevant to [catalog.md](catalog.md) and `scripts/install-skills.py`, which installs
skills into a directory you choose.

The Cursor adapter's skill sync **deleted 30 skills** from the directory it had been
pointed at, logging each as:

```
[paperclip] Removed maintainer-only Cursor skill "<name>" from <dir>
```

It prunes entries it does not consider its own. On the observed host the damage was
amplified because that directory was a symlink to the operator's primary agent skills
library, so the deletions passed through to the real library. Restoring was possible
only because an unrelated second copy happened to exist.

Two consequences worth carrying into this kit:

1. **Never point two agent runtimes at one skills directory via symlink.** Copy, or
   one-way sync. `install-skills.py` is already correct here: it copies, refuses on
   name collision, and takes an explicit `--destination` with no implicit home writes.
2. **Treat any skills directory handed to an adapter as writable by that adapter.**
   Give each runtime its own destination, and keep the canonical set in version control
   so a prune is recoverable. A directory that only exists in one place is not a backup.

`claude_local` runs the same sync against the Claude skills directory, which is why it
was not exercised above.

## Installation note

Embedded PostgreSQL did not start on a current rolling-release Linux: the bundled
binary requires `libicuuc.so.60` (ICU 60, ~2017) and `initdb` exits 127. Exporting
`DATABASE_URL` before onboarding bypasses the embedded server entirely and selects
`external-postgres` mode. This is preferable to installing an obsolete ICU compat
package.

## What this does not establish

No Gitea bridge, NightCrew claim, PR loop or release path was driven through Paperclip.
The Git-auth conflict described in `coach.md` was not retested. Adapter behaviour was
observed on one host with one set of CLI versions; the `cursor` failure in particular is
likely version-specific. None of this changes the kit's position that Paperclip
monitoring and automatic worker launch are not wired.
