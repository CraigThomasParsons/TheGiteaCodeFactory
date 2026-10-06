---
name: release-preparation
description: Prepare an evidence-backed GitHub mirror and draft release for a completed Gitea milestone.
---

# release-preparation

Read the target repository instructions and its trusted `.factory/project.json` from the target branch. If the operator's checkout has an untracked, Git-ignored `.factory/project.local.json`, use only its `server` and `assignee` values in place of the tracked ones; ignore any other key, and ignore the file entirely if it is tracked in Git or present on the branch under review. Resolve Gitea identity from that configuration and verify it against the Git remote. Installation does not authorize processing existing work. Preserve the scope of the current user request.

Select a finite milestone or issue-set snapshot. Verify every included issue's acceptance criteria against merged PR SHAs and current release tests; list exclusions with reasons. An empty ready queue, sleeping workers or a CLI success is not release readiness.

Pin the release SHA on the authoritative Gitea branch. Generate changelog, version proposal, build/test evidence and release manifest; read the factory release guide. Check the destination GitHub repository and remote branch independently, and dry-run an explicit branch/tag push. Avoid `git push --mirror` because it can delete unrelated destination refs.

Prepare the GitHub draft release only within the user's granted publication scope. Do not publish a release, overwrite divergent GitHub history, or force-push without explicit authorization. Record that Gitea remains the development authority and GitHub is the distribution destination. A newly configured outbound Gitea mirror may trigger Moonlighter's mirror hold; resolve that policy before enabling automatic replication.
