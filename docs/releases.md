# GitHub mirroring and release preparation

This is the intended final stage, not an already-proven deployment. Gitea remains
the working authority; the equivalent GitHub repository distributes reviewed releases.
For this kit, GitHub origin is `CraigThomasParsons/TheGiteaCodeFactory`; each product
has its own explicit mapping, which must be verified before writing.

## Readiness gate

Freeze a release cohort (milestone or snapshot of issue IDs) so new backlog does
not move the finish line forever. For every included issue record acceptance criteria,
merged PR URL/SHA and evidence. Explicitly document excluded/deferred work.
Block on unresolved criteria, failed tests, parked claims that belong to the cohort,
or receipts from earlier revisions. An empty queue or weeks of activity is not enough.

Pin the actual release commit on Gitea. Run the full applicable release validation
there, including BDD/parity when required, build outputs and any migration checks.
Prepare `release-manifest.json` using the template, changelog, known limitations,
version proposal and asset checksums. Version selection follows each project's
existing scheme; do not automatically apply a major/minor version rule to every repo.

## Controlled mirror

Prefer an explicit release branch/tag push over an always-on Gitea push mirror.
The inspected NightCrew worker holds PRs in repositories with outbound mirrors.
Enabling such a mirror is a controller-policy change, not just a URL setting.

In a dedicated release checkout, verify Gitea's source SHA and the GitHub repository
identity and visibility. Inspect GitHub divergence before pushing. Dry-run explicit
refs, for example after substituting the real remote and branch:

```bash
git ls-remote github refs/heads/main
git push --dry-run github RELEASE_SHA:refs/heads/main
```

`RELEASE_SHA` denotes the approved commit, not a literal shell variable. If GitHub
has unrelated/divergent history, stop and reconcile it; do not force-push. Do not
use `git push --mirror`: it can delete destination refs and expose unrelated private
branches. Push only the approved branch and release tag, then compare remote SHAs.
For Git LFS, separately transfer and verify required objects; Git ref equality alone
does not prove binary assets are available. Submodule URLs must work for recipients.

## Draft and publication

Within granted GitHub-write scope, prepare a **draft** release with the exact tag,
changelog, manifest and verified assets. Verify downloads and checksums. A successful
Gitea auto-merge is not authorization to publish on GitHub; publication remains a
separate explicitly authorized transition. Record the draft URL and evidence.

Do not mark this stage proven until an isolated cohort has exercised the complete
path: issue acceptance → merged commit → release tests → matching GitHub refs →
draft release with valid assets. Rollback means stop distribution and correct the
candidate; never rewrite an already consumed release tag silently.
