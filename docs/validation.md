# Validation checkpoint — 2026-09-28

Local verification of the initial factory kit:

| Check | Result |
|---|---|
| Factory helper tests | 17 passed |
| Standalone merge-controller tests | 19 passed |
| Codex pipeline tests | 11 passed |
| Advisory reviewer tests | 25 passed |
| Imported NightCrew worker tests | 32 passed |
| Total | 104 passed |
| All 19 skill frontmatter validations | Passed |
| Python compilation and Bash syntax checks | Passed |
| Compose config, including Actions profile | Passed |
| Gitea 1.27.3 and runner 4.0.0 registry manifests | Resolved |
| Local Markdown links | No broken links |

Independent Standards and Spec reviews found four defects, fixed with regression
coverage: account cooldown shortening; JSON boolean/number equivalence in parity;
SSH/HTTPS repository lock identity; and merge success without a verified merge SHA.

These checks did not start Gitea/Actions, authenticate providers, change Paperclip,
claim NightCrew jobs, mutate PRs or publish releases. Registry manifest resolution
is not container startup validation. All live canaries listed in operations.md
remain required before enabling a project.

The next deployment packet is an isolated Gitea/Actions canary, followed by one
project's complete BDD/implementation/review/repair/merge acceptance run. Before
multi-week automatic issue delivery, resolve NightCrew issue-job retry/completion
evidence and connect coach observation/launch adapters. Final distribution needs a
separate finite-cohort GitHub draft-release exercise. These are integration tasks,
not successes implied by the unit suite.
