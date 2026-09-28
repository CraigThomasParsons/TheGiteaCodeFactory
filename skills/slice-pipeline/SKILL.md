---
name: slice-pipeline
description: Deliver an issue-backed feature slice through serial tmux phases with durable evidence and resumable supervision.
---

# slice-pipeline

Read the target repository instructions and its trusted `.factory/project.json` from the target branch. Resolve Gitea identity from that configuration and verify it against the Git remote. Installation does not authorize processing existing work. Preserve the scope of the current user request.

Read `../dispatcher/SKILL.md`, `../scrum-master/SKILL.md`, and `references/protocol.md`. Dispatch before implementation. Execute one issue at a time through `../tmux-pipeline/SKILL.md`; a NightCrew claim must cover that execution when enabled.

Use `python3 scripts/pipeline.py start --workspace <repo> --state <private-state-dir>/state.json` for the Codex-only supervisor. `status --state <path>` reports its state; inspect logs and receipts before calling it healthy. The driver stops at review waiting or a blocker; the operator controls resumption. It is not the PR auto-merge controller.

For every phase verify current Git SHA, allowed changed paths, actual tests and remote PR state. A CLI success, stale log, empty queue, or structured receipt alone is not proof. Mark issue acceptance complete only after merge and validation prove every criterion. On provider exhaustion use `../coach/SKILL.md`; a different provider requires a compatible adapter and operator-authorized registry entry, not silently passing it Codex flags.
