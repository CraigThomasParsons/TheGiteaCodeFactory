# Moonlighter — Context Glossary

This file defines the language of Moonlighter, whose code and configuration
still use its original name, TheNightCrew. It is a glossary, not a spec:
no implementation details, no decisions. When a term here conflicts with how a
word is used in code or conversation, this file wins — or this file is wrong and
should be fixed. Decisions live in [`docs/adr/`](docs/adr/).

---

## TheNightCrew
The central coordinator: a job board with a live dashboard and an API. It
decides **who works what**, but it does not execute the work itself. Exactly one
instance is authoritative at a time.

## Worker
One computer that runs night-shift work. Its identity is a `worker_id` (for
example, its hostname). A Worker **declares the repositories it serves**; it is
only ever handed Jobs for repositories it can actually run. Workers are
first-class and plural — TheNightCrew is built to coordinate several at once.

## Night-crew client
The per-repository runner on a Worker (in practice, a cron entry). It
authenticates to TheNightCrew, **pulls** its next Job, runs that Job locally,
and **reports status back**. It is the only thing that executes agent work; the
client, not TheNightCrew, holds the working copy and invokes the agent.

## Job
One unit of agent work for one repository. Every Job has a **kind**:

- **Issue Job** — one-time. It *references* a tracker issue but is never itself
  that issue. It reaches a terminal state when the work is done.
- **Maintenance Job** — recurring. It has no tracker ticket and never reaches a
  terminal state; it becomes workable again whenever it is next due.
- **Pull Request Job** — one immutable review, resolution, arbitration, or
  post-merge stage pinned to a Gitea head and base revision. It carries an
  unguessable claim token and a structured evidence receipt.

## Claim
The authoritative record that a particular Worker holds a particular Job. A Job
that is claimed is off-limits to other Workers (with one deliberate exception —
see *Contested*). The Claim is what makes "who's working what" unambiguous.

## Contested
A property of an Issue Job that permits more than one Worker to hold it at once,
on purpose — letting several Workers race the same issue into competing results.
Maintenance Jobs are never Contested. Issue Jobs are not Contested by default.

## Fence
The human-visible reflection of a Claim onto the tracker issue (assignee,
status, a comment). It is how humans and the crew hand work back and forth using
the mechanism humans already use. The Fence mirrors the Claim; it is not itself
the authoritative Claim.

## Caller
Anything that creates Jobs by calling the intake. A Caller is not part of
TheNightCrew's core; it is any tool, scan, or person that has work to enqueue.

## Intake
The single way Jobs enter the board: an authenticated request that adds a Job
for a named repository. Every Caller goes through Intake; there is no side door.

## Due
The condition under which a Maintenance Job becomes workable again, derived from
when it last ran and how often it is meant to run. An Issue Job is never "due" —
it is workable until it is done.
