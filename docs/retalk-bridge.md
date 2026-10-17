# retalk bridge: automatic messages between Claude Code and Codex

The [retalk-bridge skill](../skills/retalk-bridge/SKILL.md) lets a Claude Code
session and a Codex session on the same computer message each other over
[retalk](https://pypi.org/project/retalk/) without a person relaying. This page
explains how it works, how to install it and what it does not do.

**Terms.** *retalk* is an end-to-end-encrypted message bus: each participant
has an *identity directory* (keys plus a local store) and a mailbox on a
*relay* server, and `retalk send|receive --dir DIR --peer NAME` moves messages.
A *side* here is one agent runtime plus the retalk identity it uses. A *hook*
is a command the agent CLI runs at a lifecycle event (session start, prompt
submitted, turn finished) whose output can add context or keep the turn going.

## Prerequisites

- Python 3.9 or later, Bash, and a systemd user session if you want the watcher.
- retalk installed (`pipx install retalk`) with two identities that have each
  other as contacts, both pointing at the same relay. A relay you run yourself
  is recommended; the public test relay has no uptime guarantee.
  The identities must be usable without an interactive prompt: created with
  `--no-passphrase`, or with a passphrase supplied through `RETALK_PASSPHRASE_FILE`
  in the environment the hooks and the timer run in.
- Claude Code with hooks support and/or Codex with the `hooks` feature (stable
  and on by default since Codex 0.15x). Verified with Claude Code 2.1.300–2.1.302
  and codex-cli 0.154.0 on Linux.

## How it works

```text
peer sends ──► relay ──► retalk receive (destructive) ──► spool (private, deduplicated)
                                                              │
                         live session: hook adds context ◄────┤
                         idle side: watcher resumes CLI  ◄────┘──► reply ──► retalk send
```

1. **Spool.** The relay never serves a message twice, so the bridge always
   receives under a lock and writes each message to
   `~/.local/state/retalk-bridge/<side>/spool.json` (owner-only) before acting.
   It passes `--save`, so `retalk history` also has both directions.
2. **Hooks.** For a session whose working directory is listed in the side's
   `hook_cwds`, `SessionStart` and `UserPromptSubmit` inject unread messages as
   additional context, and `Stop` returns `{"decision": "block"}` so the
   agent continues and can answer. `Stop` blocks at most once per turn (it does
   nothing when the event says `stop_hook_active`) and only for messages the
   agent may still answer under `max_hops`; messages at or past that limit,
   including those the watcher held, are shown at the next `SessionStart` or
   `UserPromptSubmit` instead. The reply command offered to the agent carries
   `--hop`, so replies from a live session count towards the same limit.
   Both CLIs use the same hook JSON shapes. Outside those directories the hook
   does nothing, so unrelated automated sessions never consume the mailbox.
3. **Watcher.** `retalk-bridge.timer` runs `retalk_bridge.py tick` every
   minute. For a side with unread mail it runs, read-only:
   - Claude: `claude -p [extra_args] --output-format json [--resume ID] PROMPT`
   - Codex: `codex exec --json --skip-git-repo-check -s read-only -C DIR PROMPT`,
     then `codex exec resume ID --json … PROMPT` on later wakes.

   The final answer is sent back with a hop marker. By default the watcher uses
   its own session per side (`resume_target: "bridge"`) so it never writes into
   a conversation you have open in a terminal; `"latest"` resumes the last
   hook-seen session once it has been quiet for `idle_seconds` and ended its turn.
   What the watcher answered is shown to your live session at its next prompt.

## Living with another receiver

`retalk receive` hands each message out once, so two programs receiving for
the same identity split its mail between them. If something already receives
for an identity — for example the agent-talk plugin's background follower,
which writes `<user>/inbox.ndjson` — point that side at the file instead:
`"inbox_file": "~/.agent-talk/users/alice-codex/inbox.ndjson"` (installer:
`--codex-inbox FILE`). The bridge then reads new lines from that file (byte
cursor plus id deduplication), never calls `retalk receive` for the side, and
ignores records older than `inbox_since` and records from anyone other than
`peer` (or `peer_fingerprint`). Check with `ps -ef | grep "retalk receive"`
before installing. If that receiver also injects messages into live sessions
(agent-talk does, through Claude Code monitors and an optional Codex hook),
leave `hook_cwds` empty to avoid showing a message twice and use the bridge
only for the idle-side watcher.

## Safety and quota rules

| Risk | Guard |
|---|---|
| Lost messages | Spool written under a lock before any processing |
| Duplicates | Message id deduplication in the spool |
| Provider limit | Classified from the CLI output; side benched until the reset time it names, else `default_backoff_minutes`; the message stays queued and the attempt is not counted |
| Codex already out of quota | Latest `~/.codex/sessions` log's `rate_limits` checked before any model call |
| Endless retries | `max_attempts_per_message`, then the message is marked `dead` |
| Repeated failures | Circuit breaker: `circuit_breaker_failures` failures open it for `circuit_open_minutes` |
| Spend | `max_resumes_per_hour` per side; one resume per side at a time |
| Agents answering each other forever | Hop counter: a reply is sent only while its hop ≤ `max_hops`; a message past the limit is held and shown to a live session at its next prompt, for a person to decide |
| Prompt injection | Messages are labelled as coming from another agent, not the user; watcher runs are read-only (`-s read-only`, `--disallowedTools` in the example config) |

Rate-limit text the bridge recognises (observed and documented forms): Claude
`You've hit your session limit · resets 5:20pm (America/Toronto)` with
`apiErrorStatus 429` or `is_error`; Codex `turn.failed` with a usage-limit
message and `Try again in …`; generic `429`, `rate limit`, `quota exceeded`,
`RESOURCE_EXHAUSTED`. A clock time without a date is taken in the local zone.

## Install and remove

Working directory: a checkout of this kit.

```bash
bash skills/retalk-bridge/scripts/install.sh \
  --claude-identity ~/.retalk/alice-claude --claude-peer alice-codex \
  --codex-identity ~/.retalk/alice-codex --codex-peer alice-claude \
  --hook-cwd ~/Code/my-project --watcher
bash skills/retalk-bridge/scripts/uninstall.sh            # keeps config and spool
bash skills/retalk-bridge/scripts/uninstall.sh --purge    # deletes them too
```

Names and paths above are examples. The installer copies the helper to
`~/.local/share/retalk-bridge/`, writes `~/.config/retalk-bridge/config.json`
(from [the example](../skills/retalk-bridge/templates/config.example.json)) if
absent, backs up `~/.claude/settings.json`, `~/.codex/config.toml` and
`~/.codex/hooks.json` as `<file>.bak-retalk-bridge-<timestamp>`, merges its hook
entries (it adds Codex hooks to `hooks.json` and does not edit `config.toml`),
and records everything in `~/.local/share/retalk-bridge/install-manifest.txt`.
Re-running replaces its entries instead of duplicating them. Use `--dry-run`
to preview.

After installing: trust the new Codex hooks with `/hooks` (Codex skips
untrusted hooks), and restart open Claude Code sessions (hooks load at start).

## Operating it

```bash
python3 ~/.local/share/retalk-bridge/retalk_bridge.py status          # counts, bench, circuit; no text
python3 ~/.local/share/retalk-bridge/retalk_bridge.py send --side claude "hello"
journalctl --user -u retalk-bridge.service                            # watcher runs
```

Each side's event log is `~/.local/state/retalk-bridge/<side>/bridge.log`
(JSON lines: received, resume_started, resume_ok, rate_limited, skipped_*,
sent). Delete a side's `health.json` to lift a bench early.

## Limits

- The watcher replies from its own session, so the answering agent does not
  see your open terminal conversation unless you choose `resume_target: "latest"`.
- A live session that is idle at its prompt sees new messages only at the next
  prompt or turn end; the watcher answers in the meantime.
- Only one peer per side and one machine are supported; groups are not.
- Codex and Claude Code change hook and output formats between releases; the
  outside-in tests use recorded shapes, not live CLIs.
