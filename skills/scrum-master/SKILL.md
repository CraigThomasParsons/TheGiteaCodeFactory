---
name: scrum-master
description: Supervise issue-backed delivery, identify stalled work and blockers, and reconcile queue progress.
---

# scrum-master

Read the target repository instructions and its trusted `.factory/project.json` from the target branch. Resolve Gitea identity from that configuration and verify it against the Git remote. Installation does not authorize processing existing work. Preserve the scope of the current user request.

Use `../supervise-agent-pipeline/SKILL.md` to distinguish active, waiting, blocked, rate-limited and finished workers. NightCrew is the claim authority; tracker labels are its visible reflection. Observe claims, process identity, heartbeats, receipts and PR state before changing ownership.

Ensure discoveries have tracker issues. Resolve infrastructure blockers within scope. On confirmed provider limits, run `../coach/SKILL.md`; on authentication errors or ambiguous live writers, park the task. Verify each receipt against actual repository state and tests. Completed PR preparation is ready for review, not done. Continue dependency-ready work until the requested batch ends or every remaining task has an explicit blocker.
