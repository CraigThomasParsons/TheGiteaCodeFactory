# The Gitea Code Factory

A documented software factory: described features become executable BDD contracts,
issue-backed implementation, demonstrated parity, reviewed and repaired PRs,
and finally a GitHub mirror and release candidate.

It is written for people who self-host Gitea and want AI coding agents (Codex,
Claude, Gemini and others) to deliver a queue of features over days or weeks
without a human babysitting each step, and without trusting an agent's word that
it finished. Every stage has to leave evidence the next stage can check.

The moving parts:

- **Gitea** is the development authority: issues, PRs, merged code.
- A **coordinator** owns the durable job queue and decides which worker computer
  claims which job. The author uses TheNightCrew, which is not yet published; see
  [nightcrew.md](docs/nightcrew.md) for the contract a substitute has to meet.
- **Workers** run each issue through a tmux pipeline of fresh agent sessions.
- The **coach** benches rate-limited accounts and hands the same task to another
  eligible agent.
- A separate **PR controller** reviews, repairs and auto-merges under project policy.
- **GitHub** is the downstream distribution destination for finished releases.

New to the vocabulary (slice, oracle, parity, claim, receipt, bench)? Read the
[glossary](docs/glossary.md) first.

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

0. [Glossary](docs/glossary.md): the terms used everywhere else.
1. [Architecture and lifecycle](docs/lifecycle.md): ownership, gates, multi-week completion.
2. [Gitea and Actions setup](docs/setup.md): a new Gitea install, or adding Actions to one you already run.
3. [Skills and scripts catalog](docs/catalog.md): what to install and invoke.
4. [Project onboarding and rollout](docs/onboarding.md): one canary, then each repository.
5. [Review, resolve and auto-merge](docs/pr-loops.md).
6. [BDD, TDD and parity](docs/testing.md).
7. [Coach and Paperclip](docs/coach.md): bench → checkpoint → handoff.
8. [Paperclip adapters](docs/paperclip-adapters.md): observed behaviour, and why run status is not a failure signal.
9. [Coordinator (TheNightCrew)](docs/nightcrew.md): the queue/claim contract and known gaps.
10. [GitHub mirroring and release preparation](docs/releases.md).
11. [Operations](docs/operations.md): resume, rollback, secrets, validation.

## Included versus integrated

| Component | Included here | Deployment status |
|---|---|---|
| Gitea + Actions | `docker-compose.yml`, runner config, bootstrap, smoke workflow | Deployment recipe; you run it |
| Skills | Portable instructions and supporting scripts | Install explicitly; the installer never overwrites skills you already have |
| Gemini advisory review | Adapted existing reviewer, tests, workflow template | Needs repository secrets/configuration and canary |
| Codex review/repair/merge | Skills and tested deterministic merge helper | Operator-controlled project enrollment |
| tmux pipeline | Fresh-context Codex phase driver and tests | Host tools/authentication required |
| NightCrew PR worker | Worker client snapshot in `integrations/nightcrew` | Needs a coordinator implementing the TheNightCrew API, which is not included |
| Coach | Tested bench/handoff helper and controller contract | Paperclip monitoring and automatic worker launch are not wired |
| BDD/parity | Skills, crosswalk example and report comparator | Projects supply actual step bindings, fixtures and runner |
| GitHub releases | Readiness/mirror/release runbook | Final stage has not been exercised end-to-end |

This repository does not enable services, sweep repositories, run agents, merge
PRs or publish releases just by being cloned. Configure one controller per
repository. The intended destination is all enrolled Gitea projects; each needs
its own validation and readiness evidence.

## Project status and the examples in this guide

This kit was extracted from the author's own setup, where it drives several
personal projects on a home Gitea server. Those projects appear in places as
worked examples, most often **AgileMedievalPeasantBoard**, a Laravel/PHP browser
game being migrated to a new stack. That migration is why the guide talks about
oracles, ports and parity; a greenfield project can skip those parts. You do not
need access to any of those repositories: wherever one is mentioned, the
surrounding text says what it illustrates.

The unit-tested helpers work as documented. Several live integrations have not yet
been exercised end to end; the table above and [validation.md](docs/validation.md)
say which. Treat this as a documented blueprint with working parts, not a turnkey
product.

## Local validation

Requires Linux, Python 3.11+, Node 22+, Git, Bash and Docker Compose for config validation.
Host execution additionally needs tmux and authenticated agent CLIs.

```bash
bash scripts/check.sh
```

No provider API calls, PR mutations or Docker services are launched by that check.
[Validation results](docs/validation.md) distinguish tested helpers from live canaries.
[Provenance](docs/provenance.json) records where each imported file came from on the
author's machine and its original hash.

## License

[MIT](LICENSE): use, copy, modify and redistribute freely, keeping the copyright
notice. Some skills are adapted from third-party MIT-licensed work; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
