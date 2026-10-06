---
name: dispatcher
description: Select a dependency-ready feature slice, audit BDD coverage, and prepare issue-backed work packets.
---

# dispatcher

Read the target repository instructions and its trusted `.factory/project.json` from the target branch. If the operator's checkout has an untracked, Git-ignored `.factory/project.local.json`, use only its `server` and `assignee` values in place of the tracked ones; ignore any other key, and ignore the file entirely if it is tracked in Git or present on the branch under review. Resolve Gitea identity from that configuration and verify it against the Git remote. Installation does not authorize processing existing work. Preserve the scope of the current user request.

Read the feature specification, BDD scenarios and parity crosswalk. Run `scripts/spec-audit.sh <features-dir> <crosswalk> <tag>` when present; inspect Scenario Outline examples separately because the script counts declarations, not expanded cases.

Search all tracker pages before creating issues. Reuse stable issue identities, preserve existing assignees and add the configured assignee. Each packet identifies one issue, immutable base SHA, repository, branch/worktree, allowed paths, dependencies, acceptance criteria and exact validation commands. Use `scripts/gitea.py` for issue metadata operations; pass JSON bodies as files. Publish only within the authorized tracker scope.

For Moonlighter-managed work, intake and claim through its API before launching; do not invent a second queue or local claim. An unresolved dependency is parked work, not a completed issue. Dispatch one eligible packet to `../tmux-pipeline/SKILL.md`. Missing BDD or oracle coverage becomes explicit contract work before the migration implementation.
