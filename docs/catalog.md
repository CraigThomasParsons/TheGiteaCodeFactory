# Skills and scripts catalog

Install the complete `skills/` directory using `scripts/install-skills.py`; sibling
references expect these folders together. Each `SKILL.md` explains when to invoke it
and what evidence it produces. Skill installation does not install agent binaries,
authenticate accounts, configure project tests or start a daemon.

Give each agent runtime its own destination directory and never share one between two
runtimes via symlink: an adapter's skill sync has been observed deleting entries it does
not recognise from the directory it was pointed at. See
[paperclip-adapters.md](paperclip-adapters.md).

## Workflow skills

| Skill | Role and expected result |
|---|---|
| [bdd](../skills/bdd/SKILL.md) | Approved feature → executable scenarios and acceptance crosswalk |
| [tdd](../skills/tdd/SKILL.md) | One red behavioral test → minimal implementation → refactor |
| [parity](../skills/parity/SKILL.md) | Frozen oracle and port → repeated, green matching observations |
| [dispatcher](../skills/dispatcher/SKILL.md) | Coverage/dependency audit → ready issue packet |
| [slice-pipeline](../skills/slice-pipeline/SKILL.md) | Serial delivery across a slice with durable state |
| [tmux-pipeline](../skills/tmux-pipeline/SKILL.md) | Fresh IMPL, SIMPLIFY, ARCHITECTURE, REVIEW and PR contexts |
| [simplify](../skills/simplify/SKILL.md) | Behavior-preserving scoped cleanup |
| [improve-codebase-architecture](../skills/improve-codebase-architecture/SKILL.md) | Scoped boundary improvements before review |
| [code-review](../skills/code-review/SKILL.md) | Independent Standards and Spec review axes |
| [pr-review-resolver](../skills/pr-review-resolver/SKILL.md) | Human feedback repair on the existing PR; draft replies |
| [pr-review-loop](../skills/pr-review-loop/SKILL.md) | Exact-head review and validated clearance |
| [pr-resolve-loop](../skills/pr-resolve-loop/SKILL.md) | Repair findings, validate, push and request re-review |
| [pr-review-resolve-loop](../skills/pr-review-resolve-loop/SKILL.md) | Bounded review/repair with a separate deterministic merge gate |
| [scrum-master](../skills/scrum-master/SKILL.md) | Supervision, blockers and evidence reconciliation |
| [supervise-agent-pipeline](../skills/supervise-agent-pipeline/SKILL.md) | Process/receipt classification before phase advancement |
| [coach](../skills/coach/SKILL.md) | Rate-limit observation → account bench → same-task handoff |
| [moonlighter](../skills/moonlighter/SKILL.md) | Coordinator intake/claims and job lifecycle boundaries |
| [coordinate-cross-project-work](../skills/coordinate-cross-project-work/SKILL.md) | Dependency packets and evidence across repositories |
| [release-preparation](../skills/release-preparation/SKILL.md) | Completed cohort → explicit GitHub refs and draft release evidence |

The BDD, parity, coach, Moonlighter and release skills were written for this kit.
The TDD, review and phase skills and scripts were adapted from the author's working
agent setup; [provenance.json](provenance.json) records their origins. Only skills
that belong to the delivery and testing workflow are included.

## Executable helpers

| Path | Inputs / behavior | Dependencies |
|---|---|---|
| `scripts/bootstrap.sh` | Creates local `.env` and empty ignored runner-token file; validates Compose, starts nothing | Bash, Docker Compose |
| `scripts/install-skills.py` | `--destination`; installs all skill dependencies, fails before copying on a name collision | Python |
| `scripts/check.sh` | Full local validation; runs check-ci.sh then check-local.sh | Python, Node, Bash, Docker Compose |
| `scripts/check-ci.sh` | Runner-safe subset: tests, compile, shell syntax. No Docker. This is what CI runs | Python, Node, Bash |
| `scripts/check-local.sh` | Compose config parse; skips with a notice when the Docker CLI is absent | Docker Compose |
| `scripts/coach.py` | `--config --packet --event --state --output`; benches account and writes handoff packet, no launch | Python, Linux advisory locks |
| `scripts/parity.py` | Four report paths: oracle twice, port twice; blocks red or unequal outcomes | Python |
| `scripts/reviewer/ai_pr_reviewer.js` | Gitea/project/provider environment; posts advisory review | Node 22+, Gitea token and provider access |
| `skills/dispatcher/scripts/gitea.py` | `list --repo`; bounded metadata requests with JSON body files | Python, Gitea credentials |
| `skills/dispatcher/scripts/spec-audit.sh` | Feature dir, crosswalk, tags; detects coverage drift, not test execution | Bash, GNU-style text tools |
| `skills/slice-pipeline/scripts/pipeline.py` | `start/run/status/phase`; fresh-context Codex driver and receipt schema | Python, Git, tmux, authenticated Codex |
| `skills/tmux-pipeline/scripts/verify-freshness.sh` | Worktree and logs; timestamp staleness aid | Bash, Git, stat/date |
| `skills/supervise-agent-pipeline/scripts/classify_execution.py` | Observation JSON on stdin → classified worker state on stdout | Python |
| `skills/pr-review-resolve-loop/scripts/gitea_merge.py` | Explicit repo/PR/method/receipt; read-only unless `--execute` | Python, Gitea token, private receipts |

All factory-level paths above are relative to this checkout. Installed phase
helpers resolve sibling skills relative to their own path. Factory-level coach and
parity commands still require this checkout; retain it at the recorded revision.
Scripts do not implicitly share configuration: project JSON guides the controller;
CLI flags and environment configure the executables as documented.

## Moonlighter worker client

| Module in `moonlighter/scripts/` | Purpose |
|---|---|
| `gitea-night-worker` | Host launcher and paused-state gate |
| `gitea_night/worker.py` | Discovery, claims, review/resolve stages and time windows |
| `gitea_night/coordinator.py` | Moonlighter API client |
| `gitea_night/gitea.py` | Gitea API boundary, pagination and state publication |
| `gitea_night/agents.py` | Existing Claude-first/Codex-fallback subprocess adapters |
| `gitea_night/policy.py` | Trusted target-branch checks and policy |
| `gitea_night/merge.py` | Deterministic Moonlighter merge controller |
| `gitea_night/runtime.py` | Inherited lock handling for workers |
| `gitea_night/metrics.py` | Recorded worker metrics/reporting |

The worker client has its own `night:*` labels, schemas and scheduling, and is not
yet wired to the coach. The Moonlighter server alongside it is described in
[moonlighter/README.md](../moonlighter/README.md). Read the
[known gaps](moonlighter.md#known-gaps-before-a-multi-computer-rollout) before
running any stage.

## Provider/runtime boundaries

The portable tmux driver is Codex-specific. The Moonlighter worker client has separate
Claude and Codex adapters. Cursor/Paperclip/Gemini agent-worker launch integration
requires a validated adapter; the Gemini **advisory reviewer API** is already a
separate included script. The coach cannot make a provider compatible by changing
its name. Keep provider credentials on the worker host and select explicitly
configured accounts; preserve the same issue and phase on failover.
