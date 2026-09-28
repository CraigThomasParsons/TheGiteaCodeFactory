# Roadmap

Where this kit is going: from a set of skills and scripts you assemble by hand to
a free tool other people can install and run, the way people run
[Paperclip](paperclip-adapters.md). This page is a plan, not a record of
finished work; [validation.md](validation.md) says what works today.

## The goal

**An evidence-gated delivery pipeline for self-hosted Gitea.** Agent supervisors
such as Paperclip start agents and report on them, but they trust exit codes: a
run refused with HTTP 429 can still be reported as `succeeded`. This tool's
purpose is the opposite. Nothing counts as done without proof tied to an exact
commit, and when an agent stops partway through, another one continues from
where it left off instead of starting over. It should run alone or alongside a
supervisor like Paperclip.

## Milestones

| # | Milestone | Why it comes here |
|---|---|---|
| 1 | [Prove the review loop live](#1-prove-the-review-loop-live) | Nobody should rely on a loop that hasn't completed once |
| 2 | [Gitea issues as handover documents](#2-gitea-issues-as-handover-documents) | Work must survive an agent stopping, the way it survives a person going home sick |
| 3 | [A built-in coordinator](#3-a-built-in-coordinator) | Other people can't get TheNightCrew, so today they can't run the full factory |
| 4 | [One-command project setup](#4-one-command-project-setup) | Onboarding is nine manual steps |
| 5 | [A background service and dashboard](#5-a-background-service-and-dashboard) | Replace cron and babysitting tmux; show what every agent is doing |
| 6 | [More agents](#6-more-agents) | The implementation pipeline only drives Codex |

## 1. Prove the review loop live

Create a small public demo repository on a fresh Gitea and take real PRs
through it:

- [ ] Actions smoke test and `pr-validation.yml` run on the bundled runner
- [ ] A PR with a deliberate defect goes `review:requested → review:findings →
      review:resolved → review:requested → review:clear` and merges
- [ ] Pushing a new commit after `review:clear` blocks the merge (stale-head rejection)
- [ ] A failing test blocks the merge even when the review is clear
- [ ] Record the run in [validation.md](validation.md)

The demo repository then becomes the example for the README and a blog post.

## 2. Gitea issues as handover documents

### How people do it

1. Rob looks at the scrum board, takes a ticket, assigns it to himself and
   starts work.
2. At the end of the day he pushes his commits to his branch and leaves a comment
   on the ticket saying where he left off.
3. The next day Rob calls in sick.
4. No problem: the scrum master asks John to take the ticket, and John picks up
   where Rob left off, from the branch and the comment.

The factory should work the same way, with the **Gitea issue as the handover
document**. Anyone, human or agent, should be able to open the issue and see
who has it, which branch and commit the work is on, what is done, what is next
and what is blocking it. No knowledge should live only inside an agent's session.

For agents, "calling in sick" is usually a rate limit. It can also be a crash,
a lost network connection, a dead worker computer or an expired login.

### What exists today

- The [coach](coach.md) can pick the next eligible agent and write a handoff
  packet (branch, worktree, commit, uncommitted changes, evidence). It only acts
  **after** it is told a rate limit happened and the old agent has stopped.
- **There is no heartbeat.** Nothing checks whether a worker is still healthy or
  about to hit its limit. The NightCrew worker only keeps its local lock held
  while its child processes run.
- Handover notes are not written to the Gitea issue. The handoff packet is a
  private JSON file.

### Signals available for "about to call in sick"

These were checked against the current tools (September 2026):

| Agent | Early warning (before the limit) | After the fact (limit hit) |
|---|---|---|
| **Claude Code** | The [status line](https://code.claude.com/docs/en/statusline) receives `rate_limits.five_hour` and `rate_limits.seven_day`, each with `used_percentage` and `resets_at`. Only for Pro/Max subscribers, only in interactive sessions, and only after the first response. | The [`StopFailure` hook](https://code.claude.com/docs/en/hooks) fires when a turn ends on an API error; its matcher can select `rate_limit`. |
| **Codex CLI** | Session logs under `~/.codex/sessions/` record `rate_limits.primary` (the 5-hour window) and `secondary`, each with `used_percent` and `resets_at`, in `token_count` events. Some older `codex exec --json` versions [emitted `null` here](https://github.com/openai/codex/issues/14728). | The same logs record `rate_limit_reached_type`; the process also exits with an error. |
| **Gemini and others** | None known. | The provider's HTTP 429 message in the run log. |
| **Paperclip-run agents** | None of its own. | A `Final error` line in the run log. The run *status* can still say `succeeded` ([details](paperclip-adapters.md)). |

So a reliable early warning exists for Claude Code and Codex, but not for every
agent. The design therefore has three layers, from cheapest to most expensive,
so a handover still happens when the cheaper layers can't.

### Layer A: early warning ("Rob wraps up before going home")

A **usage sensor** per agent reads the numbers above and writes them to a small
state file:
- For Claude Code, a status line script.
- For Codex, a reader for its session logs.

When usage in the current window passes a threshold, for example 85%, the worker
tells the agent to wrap up:

1. Finish or back out the current small step.
2. Commit and push work in progress to the issue branch.
3. Post a handover comment on the issue (format below).
4. Stop, and report `wrapped_up` with the window's reset time.

The coach then benches the account until `resets_at` and hands the issue on.
This is the best outcome, because the agent writes the note itself while it
still has budget.

### Layer B: rate-limit hook ("Rob's desk is left as it was")

When the limit is hit without warning, the agent can no longer write anything:
it has no model budget left. A **hook script** that makes no model calls does
the handover mechanically:

- Triggered by Claude Code's `StopFailure` hook with matcher `rate_limit`, by the
  Codex log signal, or by the worker spotting a 429 in the run log.
- Commits any uncommitted work to the issue branch as a clearly marked
  `wip(handover):` commit and pushes it.
- Posts a mechanical handover comment built from facts: branch, commit, files
  changed, last test command and its result, the phase, and the agent's last
  plan or todo list if it wrote one.
- Emits the confirmed `rate_limited` event (with `reset_at`) that the coach
  already accepts.

### Layer C: continuous checkpoints ("Rob leaves notes through the day")

For agents with no warning and no hook, and for crashes, the only protection is
to never let much unrecorded work build up:

- Each phase ends with a pushed commit and an updated handover comment.
- Within a long phase, the agent updates the handover comment at natural points:
  after each passing test, or every N minutes.

This costs extra tokens and a little time. It is worth it: an unrecoverable
half-finished task costs far more than a few hundred tokens of notes. Make the
interval configurable per project, and on by default for agents with no Layer A
or B signal.

### The heartbeat ("is Rob coming in today?")

The coach gets the job it was always meant to have: checking every active
worker regularly, not just reacting after a failure. On each heartbeat it
checks, per worker:

- Is the agent process still alive, and is it still the only writer on its branch?
- When did it last produce output or a commit?
- What does its usage sensor say, and how fast is usage rising?

From that it classifies the worker:

| State | Meaning | Action |
|---|---|---|
| `healthy` | Working, within budget | Nothing |
| `wrapping_up` | Near its limit | Layer A: ask it to hand over now |
| `sick` | Rate-limited, crashed, silent too long, or logged out | Confirm the process has stopped, run Layer B if it hasn't run, bench the account, reassign |
| `parked` | No eligible agent left | Label the issue, record why and when to retry |

Reassigning means what the scrum master does: change the Gitea issue's assignee
to the next agent, add a comment saying who took over and why, and start that
agent with the issue and its latest handover comment as its first instructions.
Silence alone never proves a worker is sick. The coach must confirm the old
process is gone before a second writer starts on the branch.

### Handover comment format

One comment per handover, readable by people and parseable by agents:

```markdown
<!-- factory-handover:v1 issue=42 agent=codex-primary reason=rate_limited -->
### Handover

**Branch:** `feature/issue-42` @ `3f2c1ab` (pushed)
**Phase:** IMPL, 2 of 3 acceptance criteria passing
**Stopped because:** 5-hour usage limit, resets 2026-10-01 14:00 UTC

**Done**
- ac-order-1: order accepted and returned (test `OrderSubmitTest` passing)
- ac-order-2: order appears in history (passing)

**Next**
- ac-order-3: reject unavailable items; start with the failing scenario
  `@ac-order-3` in `tests/bdd/features/orders.feature`

**Open questions / blockers**
- None

**Last check:** `npm test` → 41 passed, 1 failed (`ac-order-3`, expected)
```

The marker line lets the next agent find the latest handover reliably. Layer B's
mechanical version fills in the same fields it can derive and says which ones it
could not.

### Work items

- [ ] Handover comment format, parser and a skill section telling agents how to write one
- [ ] Usage sensors: Claude Code status line script, Codex session-log reader
- [ ] Layer A: threshold setting and a wrap-up instruction to the running agent
- [ ] Layer B: `StopFailure` hook script and log watchers that commit, push, comment and emit the coach event
- [ ] Layer C: checkpoint interval setting in `.factory/project.json`
- [ ] Coach heartbeat loop with the four states above
- [ ] Reassignment: Gitea assignee change, takeover comment, next agent started from the handover
- [ ] Tests for each path: early wrap-up, hard limit, crash with no signal, no eligible agent

## 3. A built-in coordinator

Today the full factory needs TheNightCrew, which is not published. Either:

- **Build a small coordinator into the tool** (SQLite, single machine). This covers
  most new users, who start on one computer. Recommended first.
- **Publish TheNightCrew** for multi-machine setups, or document its API well
  enough that someone could reimplement it ([nightcrew.md](nightcrew.md)).

Either way, fix the known gaps first: issue jobs need a safe requeue path, and
"done" must require merged code plus acceptance evidence.

## 4. One-command project setup

A command such as `gcf init owner/repo` that uses the Gitea API to:

- create the `review:*` labels
- add `.factory/project.json`, `pr-validation.yml` and optionally `pr-ai-review.yml`
- set up branch protection with the validation check required
- install the skills
- run the smoke workflow and report the result

This turns the nine manual steps in [onboarding.md](onboarding.md) into one.

## 5. A background service and dashboard

- A service that runs the review, resolve and implementation loops, restarts
  safely after a reboot and runs the coach heartbeat. It replaces cron jobs and
  hand-managed tmux sessions.
- A web dashboard: PRs by review label, which agent holds which issue, benched
  accounts and when they reset, and the proof behind every merge. This is the
  part that makes it feel like a product.

## 6. More agents

The implementation pipeline currently drives Codex only. Add a Claude Code
adapter first, then Gemini and others. Each adapter must provide:

- Starting a phase with the issue and its handover.
- A usage sensor, if the agent exposes one.
- A rate-limit signal.
- A reliable way to tell "finished" from "failed while looking successful".

## Principles that won't change

- Evidence over claims: exit codes, labels and timestamps are never proof.
- One writer per branch, confirmed before any handover.
- The writer doesn't review, the reviewer doesn't merge, the merge gate doesn't publish.
- The Gitea issue is the handover document; no progress lives only in an agent's session.
- Nothing starts, merges or publishes just because it was installed.
