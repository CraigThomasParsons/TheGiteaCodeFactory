# Glossary

Terms used across this guide. Where a term names a specific tool, the entry says
whether you can get it and what to substitute if you cannot.

## Prerequisite vocabulary

| Term | Meaning |
|---|---|
| **BDD** | Behavior-driven development: describe observable behavior as examples, then execute those examples as tests. |
| **Gherkin** | The `Feature`, `Scenario`, `Given`, `When`, `Then` notation used for BDD examples. A test runner and step bindings are needed to execute it. |
| **Step binding** | Test code that performs or checks one Gherkin step against the application. A `.feature` file alone is not an executable test. |
| **TDD** | Test-driven development: demonstrate a missing behavior with a failing test, implement it, then refactor while tests pass. |
| **PR** | Pull request: a proposed branch change reviewed before merging into a target branch. |
| **CI** | Continuous integration: automated checks run for proposed code changes. |
| **SHA / revision** | A Git commit identifier. Receipts use the full identifier to identify the exact tested code. |
| **Worktree** | A separate checkout managed by Git, allowing a worker to use its own branch without changing another checkout. |
| **tmux** | A terminal session manager. A detached session can keep running after its client disconnects; it does not survive a host reboot. |
| **Skill / adapter** | A skill is instructions an agent reads; an adapter is code that invokes a specific agent or external service. Installing a skill does not install that service. |
| **ADR** | Architecture decision record: a document explaining a design decision and its tradeoffs. |
| **NAS** | Network-attached storage: a server used for files; some example projects also deploy applications there. A NAS is not required by this kit. |

## People and roles

| Term | Meaning |
|---|---|
| **Operator** | The human who runs the factory: approves features, grants merge/release scope and answers questions agents cannot. |
| **Worker** | A computer (or process on it) that holds repository checkouts and runs agents. You can have several. |
| **Writer** | The one process currently allowed to change a given branch. The factory keeps exactly one writer per branch. |
| **Controller** | The process that owns a decision for a repository, such as the PR controller that decides review, repair and merge. Run one per repository, never two. |
| **Coordinator** | A service that holds the durable job queue and hands each job to one worker at a time (see *claim*). In this factory that is Moonlighter; see below. |

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
| **Receipt** | A private JSON record of what actually happened: revisions, commands, exit codes, review results. Controllers verify receipts against logs and Git/server state; a receipt is not proof by itself. |
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
| **Coach** | The planned controller behavior that notices rate limits and transfers tasks. The included helper only benches accounts and prepares handoff packets; monitoring and launching are not integrated. |
| **Bench** | Put an account on cooldown so nothing is dispatched to it until its limit resets. |
| **Handoff** | Passing an unfinished task, with its branch, worktree, dirty changes and evidence, to the next agent without restarting it. |
| **Handover comment** | A structured comment on the Gitea issue recording branch, commit, what's done, what's next and why work stopped, so another agent or person can continue. Planned; see [roadmap.md](roadmap.md#handover-comment-format). |
| **Heartbeat** | A regular health check of each worker: process alive, recent progress, usage against its limit. Planned; see [roadmap.md](roadmap.md#the-heartbeat-is-rob-coming-in-today). |
| **Exit 75** | `EX_TEMPFAIL`. Some agent adapters use it to mean "provider exhausted, retry later". Only trust it where the adapter documents that contract. |

## Tools named in this guide

| Name | What it is | Availability |
|---|---|---|
| **Gitea** | Self-hosted Git forge; the development authority here. | Public, [gitea.com](https://about.gitea.com/). |
| **Gitea Actions** | Gitea's CI, compatible with GitHub Actions workflow syntax. | Bundled with Gitea. |
| **Codex / Claude / Gemini** | Agent CLIs and model providers used by workers and the reviewer. | Public; each needs its own account. |
| **Paperclip** | An open-source control plane for supervising agent runs. Optional here; see [paperclip-adapters.md](paperclip-adapters.md). | Public. |
| **Moonlighter** | The factory's coordinator: registers repositories, labels PRs for the review loops, holds the job board and atomic claims, and shows a live dashboard. A Laravel app; its code still uses its original name, TheNightCrew. | Included in [moonlighter/](../moonlighter/). See [moonlighter.md](moonlighter.md). |
| **Sanctum token** | Laravel's API token; Moonlighter issues one per worker. Distinct from a Gitea PAT. | — |
| **PAT** | Gitea personal access token. | — |
