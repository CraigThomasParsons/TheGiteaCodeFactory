---
name: coach
description: Bench rate-limited agent accounts and prepare same-task handoffs to the next eligible agent.
---

# coach

Read the target repository instructions and its trusted `.factory/project.json` from the target branch. Resolve Gitea identity from that configuration and verify it against the Git remote. Installation does not authorize processing existing work. Preserve the scope of the current user request.

Observe actual worker output and process state. Accept confirmed rate-limit/quota evidence, including a provider-exhaustion exit 75 only from adapters that document that meaning. Separate authentication failures, test failures, network faults and human decisions; these do not trigger automatic provider rotation.

Checkpoint issue/claim, branch, worktree, current SHA, uncommitted diff, phase, commands, acceptance criteria, logs and prior attempt. Confirm the entire previous writer process tree has exited and its locks are released before setting `writer_stopped: true`. Silence or a stale pane alone is not proof of exit.

Run the factory `scripts/coach.py` with config, packet, event, private state and a new output path. It benches the account until the supplied timezone-qualified reset time, or bounded exponential backoff when unknown. Select the next installed, enabled, capable account in configured order; one attempt per account per task batch. All aliases sharing that account are benched together. No eligible account means parked, never done.

The script prepares a handoff, not an agent launch. The owning controller verifies the output, current worktree and Moonlighter claim, then invokes the matching provider adapter with the same phase and scope. Preserve unresolved diffs; do not reset or open duplicate work. A different host requires coordinator-mediated claim transfer and accessible evidence. Paperclip event ingestion and automatic launch integration remain rollout work; do not claim they exist because this helper succeeds.
