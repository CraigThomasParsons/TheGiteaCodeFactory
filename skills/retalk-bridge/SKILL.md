---
name: retalk-bridge
description: Let a Claude Code session and a Codex session message each other automatically over retalk — live sessions see new messages through hooks, and an optional watcher wakes an idle side to reply, with rate-limit backoff and loop guards.
---

# retalk-bridge

[retalk](https://pypi.org/project/retalk/) is an end-to-end-encrypted message
bus with a command-line client: each agent has an identity directory and a
mailbox on a relay. On its own, neither agent CLI checks its mailbox, so a
person has to relay every message. This skill closes that gap. The full guide
is [docs/retalk-bridge.md](../../docs/retalk-bridge.md).

Use it when two agent runtimes on one machine (one Claude Code identity, one
Codex identity) should exchange messages without a human copying them across.

## What it does

- **Hooks (live sessions).** On `SessionStart`, `UserPromptSubmit` and `Stop`
  the bridge drains the side's mailbox and hands new messages to the session
  as added context. On `Stop` it asks the agent to continue once so it can
  answer. Hooks act only in the directories listed in the side's `hook_cwds`.
- **Watcher (idle sides, optional).** A systemd user timer runs
  `retalk_bridge.py tick` every minute. When a side has unread mail and no
  limit is in force, it runs that CLI non-interactively (`claude -p --resume`
  or `codex exec resume`, read-only) with the messages as the prompt and sends
  the agent's final answer back over retalk.

## Rules the bridge enforces

- `retalk receive` is destructive, so every read goes into a private spool
  (`~/.local/state/retalk-bridge/<side>/`, mode 0700) under a file lock.
  Message ids are deduplicated. Message text never goes into Git.
- Provider limits bench the side until the reset time named in the output
  (Claude `You've hit your session limit · resets 5:20pm`, Codex
  `Try again in …` or a 100% `rate_limits` window in its latest session log,
  checked before any model call), or for `default_backoff_minutes`.
- Loop guards: one resume per side at a time (lock), `max_resumes_per_hour`,
  `max_attempts_per_message`, a circuit breaker after repeated failures, and a
  hop counter on bridge-sent replies (`[retalk-bridge hop=N]`) so two agents
  cannot answer each other forever (`max_hops`).
- Messages are presented as coming from another agent, not from the user.

## Another receiver already running?

`retalk receive` is destructive. If another program (for example the
agent-talk plugin's follower) already receives for an identity, set that side's
`inbox_file` to the NDJSON inbox it writes (`--claude-inbox` / `--codex-inbox`)
so the bridge reads that file instead of competing for the mailbox. See the guide.

## Install

From a checkout of this kit:

```bash
bash skills/retalk-bridge/scripts/install.sh \
  --claude-identity ~/.retalk/alice-claude --claude-peer alice-codex \
  --codex-identity ~/.retalk/alice-codex --codex-peer alice-claude \
  --hook-cwd ~/Code/my-project --watcher
```

The identities and contact names are examples; use the ones you created with
`retalk init` and `retalk add`. The installer backs up
`~/.claude/settings.json`, `~/.codex/config.toml` and `~/.codex/hooks.json`
with a timestamp suffix, then merges only its own entries. Codex skips new
hooks until you trust them with `/hooks`. Undo with
`bash skills/retalk-bridge/scripts/uninstall.sh` (`--purge` also deletes the
config and the spool).

## Commands

`retalk_bridge.py hook|tick|fetch|send|status` — see `--help`. To reply from a
live session: `python3 ~/.local/share/retalk-bridge/retalk_bridge.py send --side claude "text"`.
`status` prints spool counts, bench and circuit state without message text.

The helper is generated from Haxe source in `haxe/src/gcf/retalkbridge/`; do
not edit `scripts/retalk_bridge.py` by hand.
