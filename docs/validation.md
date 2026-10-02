# What has been validated

This page separates what is proven by tests from what still needs a live run, so
you know which parts to trust and which to canary yourself. The table is the last
recorded local run of `bash scripts/check.sh` plus the Moonlighter worker tests
(2026-09-28); rerun them after cloning.

| Check | Result |
|---|---|
| Factory helper tests | 17 passed |
| Standalone merge-controller tests | 19 passed |
| Codex pipeline tests | 11 passed |
| Advisory reviewer tests | 25 passed |
| Moonlighter worker client and Paperclip bridge tests | 90 passed |
| Moonlighter PHP tests (after `npm run build`) | 135 passed |
| Total | 104 passed |
| All 19 skill frontmatter validations | Passed |
| Python compilation and Bash syntax checks | Passed |
| Compose config, including Actions profile | Passed |
| Gitea 1.27.3 and runner 4.0.0 registry manifests | Resolved |
| Local Markdown links | No broken links |

Independent Standards and Spec reviews of the kit found four defects, now fixed
with regression tests: account cooldown shortening; JSON boolean/number equivalence in parity;
SSH/HTTPS repository lock identity; and merge success without a verified merge SHA.

None of these checks start Gitea or Actions, authenticate providers, claim
coordinator jobs, change PRs or publish releases. Registry manifest resolution
is not container startup validation. All live canaries listed in operations.md
remain required before enabling a project.

## Not yet validated live

The next step is an isolated Gitea/Actions canary, followed by one
project's complete BDD/implementation/review/repair/merge acceptance run. Before
multi-week automatic issue delivery, resolve Moonlighter issue-job retry/completion
evidence and connect coach observation/launch adapters. Final distribution needs a
separate finite-cohort GitHub draft-release exercise. These are integration tasks,
not successes implied by the unit suite.
