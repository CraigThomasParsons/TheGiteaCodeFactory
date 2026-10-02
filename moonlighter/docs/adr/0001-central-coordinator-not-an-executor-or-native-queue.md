# 1. TheNightCrew is a central coordinator — not an executor, and not Laravel's native queue

Date: 2026-06-20

Status: Accepted

## Context

The night-shift automation that grew up inside the author's first automated
project (a Laravel browser game) ended
up as three overlapping pieces: a shell job queue, an in-app artisan harness,
and per-repository file locks backed by a local tracker mirror. Each one pinned
a single repository and a single issue, needed the cron re-pointed by hand, and
— most importantly — could not coordinate work across **more than one computer**.

We want one place that answers "who is working what," that several computers can
ask, and that a human can watch on a screen. This ADR captures the two decisions
in that design that are expensive to reverse and surprising without the
reasoning.

## Decision

**1. TheNightCrew coordinates; it does not execute.** It is a job board, a
Livewire dashboard, a Reverb live feed, and an API. The agent work itself stays
on each Worker's own machine, behind a Night-crew client that pulls a Job, runs
it locally, and reports back. TheNightCrew never holds a working copy and never
invokes an agent.

**2. Jobs live in a custom `night_crew_jobs` table — not Laravel's `jobs`
table.** TheNightCrew's domain Jobs are durable, human-visible, claimable units
of agent work with two kinds (one-time issue, recurring maintenance) and a
human-facing fence onto the tracker. Laravel's native queue is reserved for
TheNightCrew's *own* internal async work (broadcasts, outbound tracker calls).
The two never share a table.

## Consequences

- A Worker is a first-class, plural concept from day one: Jobs are dispatched to
  Workers that declare they serve the relevant repository, and the atomic claim
  on `night_crew_jobs` — not a per-repository file lock — is the single source
  of truth for who holds what.
- Because TheNightCrew does not execute, it can stay small and always-on
  (suitable for a supervisor like systemd), while clients remain self-firing
  cron entries with nothing to supervise.
- We carry a custom table and its claim/locking logic instead of getting queue
  semantics for free. That is the deliberate price of jobs that are durable,
  visible on a board, claimable across machines, and mirrored to a tracker —
  none of which Laravel's `jobs` table models.
- The tracker (Gitea) is a human-visible *fence*, never the atomic lock: its
  labels have no compare-and-set, maintenance work has no ticket at all, and a
  tracker outage must not be able to halt the crew.

## Alternatives considered

- **Laravel's native queue / Horizon.** Rejected: native jobs are transient
  worker-side execution units with no first-class notion of a claimable,
  human-visible, cross-machine unit of work mirrored to a tracker. We would have
  fought the abstraction. Native queues are kept for internal async instead.
- **A central executor (TheNightCrew runs the agents itself).** Rejected: it
  would have to hold every repository's working copy and every machine's
  toolchain, and could not use idle capacity on the machines that already have
  them. Execution stays where the checkout and tools already are.
