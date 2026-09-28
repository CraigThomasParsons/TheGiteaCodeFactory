---
name: pr-review-resolve-loop
description: Review and repair bounded Gitea PR batches and merge only current-head cleared PRs under the project merge policy.
---

# pr-review-resolve-loop

Read the target repository instructions and its trusted `.factory/project.json` from the target branch. Resolve Gitea identity from that configuration and verify it against the Git remote. Installation does not authorize processing existing work. Preserve the scope of the current user request.

Set `GITEA_SERVER_URL` and `GITEA_TOKEN` or `GITEA_TOKEN_FILE` for the selected Gitea server. This workflow is Gitea-only; the factory repository's GitHub origin is not a target. Review `references/receipt.md` before operating.

Process at most two PRs and three repair rounds per PR, unless a smaller task bound applies. Hold one controller lock; skip drafts, bots and work owned by another controller. Paginate discovery to an empty page. Read `../pr-review-loop/SKILL.md` and `../pr-resolve-loop/SKILL.md` for review and repair. New head/base invalidates prior clearance.

After an independent clean Standards/Spec review and passing required validation, write the receipt outside the PR checkout. Derive commands and required contexts from trusted target-branch policy and server protection. Review output and `review:clear` are necessary but not sufficient. Model approval alone is advisory.

Run `python3 scripts/gitea_merge.py --repo <owner/repo> --pr <n> --method <configured-method> --receipt <receipt.json>` for read-only eligibility. Add `--execute` only when the operator enabled auto-merge for this repository and invoked the loop with that authority. The helper's flag is the execution boundary; it does not read `.factory/project.json` itself. Never force merge, bypass required checks or delete branches. Verify the merged SHA before recording completion.

The helper rechecks head/base/labels and passes `head_commit_id`. Gitea does not atomically guard base or label changes in that request, so branch protections remain required. Uncertain POST outcomes require a fresh read, not a blind retry. Stop on authentication failures, exhausted rounds, missing tests or conflicting ownership. Only reconcile acceptance criteria proven by the merged change.
