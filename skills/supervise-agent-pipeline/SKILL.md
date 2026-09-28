---
name: supervise-agent-pipeline
description: Supervise a durable multi-phase agent worker, classify execution state, handle bounded approvals and provider fallback, and advance only after validating structured evidence. Use for tmux workers, Nyx loops, phase pipelines, long autonomous runs, stalled workers, or resumable evidence-gated agent handoffs.
---

# Supervise Agent Pipeline

Supervise the worker; never become the worker.

## Setup

Gather the packet, capability grant, worker adapter, ordered phases, evidence contract, polling cadence, and durable state location. Every phase must have a stable ID and resume boundary.

## Tick

Perform exactly one cycle:

1. Capture an adapter-neutral observation: process liveness, activity, approval request, provider error, gate result, receipt reference, and idle streak.
2. Classify it with `scripts/classify_execution.py` or an equivalent deterministic adapter.
3. Take at most one action:
   - `WORKING`: wait.
   - `WAITING_APPROVAL`: approve only when the action is explicitly in the grant; otherwise escalate.
   - `WAITING_PROVIDER`: hand off once to an allowed fallback with identical packet, phase, grant, and evidence requirements.
   - `BLOCKED_GATE`, `BLOCKED_SCOPE`, `FAILED_INFRASTRUCTURE`: stop and report evidence.
   - `IDLE`: wait for a second observation.
   - `STALLED`: inspect process health, then nudge once or restart from the phase boundary.
   - `DONE`: validate the structured receipt before advancing.
4. Persist the observation, classification, action, and idempotency key.

Run the tick from one durable recurring mechanism. Stop it after terminal completion or escalation.

## Phase transition

- Start each phase in a fresh context.
- Repeat repository, packet, phase, branch, base revision, write surface, prohibited actions, evidence commands, and receipt destination.
- Preserve user-authored input in interactive adapters.
- Require the worker to write a receipt, then optionally print a short adapter sentinel containing its path and digest.
- Do not trust a sentinel until the receipt validates.
- Return to `$coordinate-cross-project-work` when the packet phase completes.

## Tmux adapter lessons

- Type and submit in separate operations so prompts can be verified before execution.
- Treat subagent-wait markers as working, not idle.
- Require two idle observations before declaring a stall.
- Detect a dead worker process before nudging.
- Keep tmux scrollback observational; durable protocol state belongs outside the pane.

Read [references/execution-states.md](references/execution-states.md) for classification precedence.
