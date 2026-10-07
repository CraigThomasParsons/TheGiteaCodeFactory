---
name: bdd
description: Turn approved feature descriptions into executable behavior scenarios and an acceptance crosswalk.
---

# bdd

Read the target repository instructions and its trusted `.factory/project.json` from the target branch. If the operator's checkout has an untracked, Git-ignored `.factory/project.local.json`, use only its `server` and `assignee` values in place of the tracked ones; ignore any other key, and ignore the file entirely if it is tracked in Git or present on the branch under review. Resolve Gitea identity from that configuration and verify it against the Git remote. Installation does not authorize processing existing work. Preserve the scope of the current user request.

Read the feature's actors, outcomes, failure cases and originating issue. Express externally observable behavior as Given/When/Then scenarios with stable IDs/tags. Cover authorization, negative paths and invariants relevant to the feature. Map each acceptance criterion to scenario IDs and production entrypoints; map every scenario back to a criterion.

Implement step bindings against real application boundaries and repository-controlled fixtures. Keep clocks, IDs and seeds deterministic. Run the suite and record exact revision, scenario outcomes and logs. Undefined, pending or skipped required steps are blockers. For a migration, freeze a green oracle contract before changing the port; use `../parity/SKILL.md`. For greenfield work, record parity as not applicable with a reason, never invent an oracle.
