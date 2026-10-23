# Provider off switch

Some kit helpers start an agent command-line tool (CLI) without anyone at the
keyboard, for example the [retalk bridge](retalk-bridge.md) waking an idle agent.
Those runs use whatever account the CLI is logged in to. If one computer is also
logged in with an account you must not use for this work (such as an
employer-provided account), switch that provider off so no helper starts it.

The switch only stops helpers in this kit from starting the CLI. It does not log
anyone out, and it does not stop you from running the CLI yourself.

## Turn a provider off

Provider names are the CLI names: `claude` (Claude Code) and `codex` (Codex CLI).
Names are not case-sensitive.

Run this in a terminal on the worker computer (any directory):

```bash
mkdir -p ~/.config/gcf
cp templates/providers.example.json ~/.config/gcf/providers.json   # from a clone of this repository
```

or write the file yourself:

```json
{"disabled": ["claude", "codex"]}
```

To turn a provider back on, remove it from the list (or delete the file).
No restart is needed: every helper reads the file each time, before starting a CLI.

For one shell, a service unit or a test, set the environment variable
`GCF_DISABLED_PROVIDERS` to a comma-separated list instead. When it is set, even to
an empty string, it replaces the file:

```bash
GCF_DISABLED_PROVIDERS=claude,codex python3 skills/retalk-bridge/scripts/retalk_bridge.py tick --side codex
```

A missing file disables nothing. A file that is not a JSON object with a
`"disabled"` list of strings also disables nothing; the helper prints a warning
starting with `ignoring` on standard error, so check that output after editing.

## What respects it

| Helper | When a provider is off |
|---|---|
| Retalk bridge watcher (`retalk_bridge.py tick`) | Starts no run and does not read new mail for that side. Logs `skipped_provider_disabled` once in the side's `bridge.log` when the switch turns on, and `provider_enabled` when it turns off. |
| Retalk bridge hooks (`retalk_bridge.py hook`) | Injects nothing into that CLI's sessions and logs `skipped_provider_disabled`. Messages wait in the mailbox until the provider is back on. |
| Slice pipeline (`skills/slice-pipeline/scripts/pipeline.py`) | `start`, `run` and `phase` refuse with a message naming the switch and exit 1; `status` still works. A running supervisor stops before its next tick. |

Not covered yet: the Moonlighter worker (`moonlighter/scripts/gitea_night/agents.py`)
and the Paperclip bridge (`moonlighter/scripts/tools/paperclip_bridge.py`).
The Paperclip bridge already accepts `"enabled": false` per provider in its own
configuration. Scheduled jobs outside this kit (cron entries, systemd timers you
wrote yourself) are also not affected; stop those separately.
