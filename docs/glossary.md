# Glossary

Terms used across this guide. Where a term names a specific tool, the entry says
whether you can get it and what to substitute if you cannot.

## People and roles

| Term | Meaning |
|---|---|
| **Operator** | The human who runs the factory: approves features, grants merge/release scope and answers questions agents cannot. |
| **Worker** | A computer (or process on it) that holds repository checkouts and runs agents. You can have several. |
| **Writer** | The one process currently allowed to change a given branch. The factory keeps exactly one writer per branch. |
| **Controller** | The process that owns a decision for a repository, such as the PR controller that decides review, repair and merge. Run one per repository, never two. |
| **Coordinator** | A service that holds the durable job queue and hands each job to one worker at a time (see *claim*). The author uses TheNightCrew; see below. |

## Work units

| Term | Meaning |
|---|---|
| **Feature / slice** | A slice is a vertical piece of a feature small enough to deliver through the pipeline: its scenarios, issues and PRs move together. Slices are often numbered and tagged, e.g. `@slice-orders`. |
| **Acceptance criteria (AC)** | The observable outcomes that make a feature done. Each has an ID such as `ac-order-1`. |
| **Crosswalk** | A table mapping every acceptance criterion to the BDD scenarios, code entrypoints, fixtures and test commands that prove it, and back. |
| **Issue packet / work packet** | The bundle handed to an agent for one issue: scope, allowed paths, criteria, base/head revisions, commands, prior evidence. |
| **Cohort** | A frozen list of issues that together make up one release, so the finish line does not move as new backlog arrives. |
| **Canary** | A deliberately small, disposable first run (one repository, one PR) used to prove a setup before rolling it out wider. |
| **Fleet / enrollment** | All repositories the factory manages; enrolling a repository means adding its configuration and controller. |

## Pipeline mechanics

| Term | Meaning |
|---|---|
| **Phases** | The fixed steps a worker runs per issue: `IMPL` (implement), `SIMPLIFY`, `ARCHITECTURE`, `REVIEW`, `PR`. Each runs in a *fresh context*: a new agent session, so no phase inherits another's assumptions. |
| **tmux pipeline** | The driver that runs each phase as a separate agent session inside tmux, so long runs survive disconnects and can be inspected. |
| **Claim** | The coordinator's atomic record that one worker owns one job. Local locks protect a branch on one machine; the claim protects it across machines. |
| **Receipt** | A private JSON record of what actually happened: revisions, commands, exit codes, review results. Gates trust receipts, not labels or timestamps. |
| **Current head** | The PR's latest commit. A review or test result only counts for the exact head it ran against; a new commit invalidates it. |
| **Park** | Stop work on a job with a recorded reason and retry condition, instead of failing it or looping. |
| **Standards / Spec review** | The two independent review axes: does the code follow the repository's standards, and does it do what the issue asked. |

## Migration terms

| Term | Meaning |
|---|---|
| **Oracle** | The existing system whose behavior is the reference, pinned to a fixed revision. Only migrations have one. |
| **Port** | The new implementation that must reproduce the oracle's contracted behavior. |
| **Parity** | Running the same scenarios against oracle and port (twice each, for determinism) and requiring identical observations. Greenfield projects mark parity *not applicable*. |

## Accounts and rate limits

| Term | Meaning |
|---|---|
| **Coach** | The logic that notices an agent account hit a rate limit and moves the same task to another eligible agent. |
| **Bench** | Put an account on cooldown so nothing is dispatched to it until its limit resets. |
| **Handoff** | Passing an unfinished task, with its branch, worktree, dirty changes and evidence, to the next agent without restarting it. |
| **Exit 75** | `EX_TEMPFAIL`. Some agent adapters use it to mean "provider exhausted, retry later". Only trust it where the adapter documents that contract. |

## Tools named in this guide

| Name | What it is | Availability |
|---|---|---|
| **Gitea** | Self-hosted Git forge; the development authority here. | Public, [gitea.com](https://about.gitea.com/). |
| **Gitea Actions** | Gitea's CI, compatible with GitHub Actions workflow syntax. | Bundled with Gitea. |
| **Codex / Claude / Gemini** | Agent CLIs and model providers used by workers and the reviewer. | Public; each needs its own account. |
| **Paperclip** | An open-source control plane for supervising agent runs. Optional here; see [paperclip-adapters.md](paperclip-adapters.md). | Public. |
| **TheNightCrew** | The author's Laravel coordinator service (job board, atomic claims, dashboard). | **Not currently published.** This guide documents its API contract and includes its worker client so you can see the shape; to run the full queue you need your own coordinator that meets the same contract. See [nightcrew.md](nightcrew.md). |
| **Sanctum token** | Laravel's API token; TheNightCrew issues one per worker. Distinct from a Gitea PAT. | — |
| **PAT** | Gitea personal access token. | — |
