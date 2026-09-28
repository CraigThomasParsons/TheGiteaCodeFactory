# The Gitea Code Factory

A documented software factory: described features become executable BDD contracts,
issue-backed implementation, demonstrated parity, reviewed and repaired PRs,
and finally a GitHub mirror and release candidate.

Gitea is the development authority. **TheNightCrew owns the durable queue and
cross-machine claims.** Workers run the tmux pipeline. The coach benches
rate-limited accounts and hands the same task to another eligible agent.
A separate PR controller reviews, repairs and auto-merges under project policy.
GitHub is the downstream distribution destination.

```mermaid
flowchart LR
  A[Features and acceptance criteria] --> B[BDD and parity contracts]
  B --> C[Gitea issues and dependencies]
  C --> D[TheNightCrew claim]
  D --> E[tmux implementation pipeline]
  E --> F[PR review]
  F -->|findings| G[PR resolve]
  G --> F
  F -->|current revision clear and tests pass| H[Auto-merge]
  H --> I[Acceptance evidence reconciled]
  I -->|more ready issues| D
  I -->|release cohort complete| J[GitHub mirror and draft release]
  E -->|rate limit| K[Coach benches account]
  K -->|same task, next eligible agent| E
```

## Start here

1. [Architecture and lifecycle](docs/lifecycle.md): ownership, gates, multi-week completion.
2. [Gitea and Actions setup](docs/setup.md): new server or existing server.
3. [Skills and scripts catalog](docs/catalog.md): what to install and invoke.
4. [Project onboarding and rollout](docs/onboarding.md): one canary, then each repository.
5. [Review, resolve and auto-merge](docs/pr-loops.md).
6. [BDD, TDD and parity](docs/testing.md).
7. [Coach and Paperclip](docs/coach.md): bench → checkpoint → handoff.
8. [Paperclip adapters](docs/paperclip-adapters.md): observed behaviour, and why run status is not a failure signal.
9. [TheNightCrew integration](docs/nightcrew.md): inspected code and known blockers.
10. [GitHub mirroring and release preparation](docs/releases.md).
11. [Operations](docs/operations.md): resume, rollback, secrets, validation.

## Included versus integrated

| Component | Included here | Deployment status |
|---|---|---|
| Gitea + Actions | `docker-compose.yml`, runner config, bootstrap, smoke workflow | Deployment recipe; not installed on the existing server |
| Skills | Portable instructions and supporting scripts | Install explicitly; existing skills are preserved |
| Gemini advisory review | Adapted existing reviewer, tests, workflow template | Needs repository secrets/configuration and canary |
| Codex review/repair/merge | Skills and tested deterministic merge helper | Operator-controlled project enrollment |
| tmux pipeline | Fresh-context Codex phase driver and tests | Host tools/authentication required |
| NightCrew PR worker | Source snapshot and provenance in `integrations/nightcrew` | Requires a compatible separately deployed coordinator |
| Coach | Tested bench/handoff helper and controller contract | Paperclip monitoring and automatic worker launch are not wired |
| BDD/parity | Skills, crosswalk example and report comparator | Projects supply actual step bindings, fixtures and runner |
| GitHub releases | Readiness/mirror/release runbook | Final stage has not been exercised end-to-end |

This repository does not enable services, sweep repositories, run agents, merge
PRs or publish releases just by being cloned. Configure one controller per
repository. The intended destination is all enrolled Gitea projects; each needs
its own validation and readiness evidence.

## Local validation

Requires Linux, Python 3.11+, Node 22+, Git, Bash and Docker Compose for config validation.
Host execution additionally needs tmux and authenticated agent CLIs.

```bash
bash scripts/check.sh
```

No provider API calls, PR mutations or Docker services are launched by that check.
[Validation results](docs/validation.md) distinguish tested helpers from live canaries.
[Provenance](docs/provenance.json) records captured local sources. Adaptations
remove project defaults; upstream code has not been relicensed.
