---
name: pr-review-loop
description: Review the exact current Gitea PR revision and publish findings or validated clearance.
---

# pr-review-loop

Read the target repository instructions and its trusted `.factory/project.json` from the target branch. If the operator's checkout has an untracked, Git-ignored `.factory/project.local.json`, use only its `server` and `assignee` values in place of the tracked ones; ignore any other key, and ignore the file entirely if it is tracked in Git or present on the branch under review. Resolve Gitea identity from that configuration and verify it against the Git remote. Installation does not authorize processing existing work. Preserve the scope of the current user request.

Read `../pr-review-resolve-loop/SKILL.md` and its receipt contract. Select up to two explicitly enrolled PRs with `review:requested`. Pin head/base SHAs and both repository/branch identities. Acquire controller ownership and inspect trusted base-branch instructions and originating issue.

Run `../code-review/SKILL.md` with independent Standards and Spec reviewers, no edits. Re-fetch the PR before publishing. A moved head/base requires another review. Publish a report carrying `<!-- gitea-codex-review:v1 head=<sha> base=<sha> findings=<n> -->`. Findings set `review:findings`; zero findings become `review:clear` only after required checks pass and the controller verifies a matching receipt. Preserve unrelated labels. Standalone invocation permits requested review reports and state labels, not repairs or merging.
