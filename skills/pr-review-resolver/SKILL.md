---
name: pr-review-resolver
description: Address human feedback on an existing PR branch and draft replies without posting them.
---

# pr-review-resolver

Read the target repository instructions and its trusted `.factory/project.json` from the target branch. Resolve Gitea identity from that configuration and verify it against the Git remote. Installation does not authorize processing existing work. Preserve the scope of the current user request.

Keep the existing PR and issue. Pin current head/base, inspect each review finding, repair valid defects and rerun affected checks. Preserve completed phase history, invalidate stale evidence and create a fresh REVIEW receipt. Push normal scoped commits when authorized. Draft replies for the operator without posting or resolving threads. Hand back to the configured PR controller; do not merge here.
