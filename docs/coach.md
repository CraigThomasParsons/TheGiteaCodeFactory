# Coach: bench, checkpoint, hand off

## Why a coach is needed

Agent accounts hit usage limits. Without intervention the task stalls, or worse,
is recorded as done. The required behavior is:
**observe rate limit → bench that account → preserve the same task → hand off to
the next eligible agent**. A failure is never task completion.

Do not assume an agent supervisor provides this behavior. In the recorded
[Paperclip field observations](paperclip-adapters.md), some provider failures were
reported as successful runs and no automatic reassignment was observed. Those
results are version-specific; test the supervisor and adapters you deploy.
The factory helper computes a deterministic, testable handoff from a confirmed event.

What it doesn't do yet: there is no heartbeat, so nothing notices a worker
nearing its limit or going silent, and handover notes are not written to the
Gitea issue. The [roadmap](roadmap.md#2-gitea-issues-as-handover-documents)
describes the planned early-warning, hook and heartbeat design.

## Shipped helper

`scripts/coach.py` persists a private account cooldown ledger and emits a new handoff
packet. It does not scrape Paperclip, kill workers or start provider CLIs. It provides
the deterministic transition for a controller to call after observing actual events.

Prepare private copies of the three `templates/coach-*.example.json` files. Enable
only installed and authorized accounts, ordered by preference. All workers sharing
a provider/account quota must use the same `account` ID. Keep capabilities honest:
an agent with read-only permissions cannot implement or repair code.

```bash
python3 scripts/coach.py \
  --config /private/agents.json --packet /private/task.json \
  --event /private/rate-limit.json --state /private/coach/ledger.json \
  --output /private/coach/attempt-2.json
```

The sample event sets `writer_stopped: false` deliberately. The controller must
observe process-tree exit and lock release before setting it true. The flag is
reported evidence, not independent process verification by this script.

Use provider-supplied `reset_at` with timezone when available; otherwise backoff
starts at 60 seconds and increases up to six hours. Benching applies across tasks
sharing the same ledger/account. Within a task batch each account is attempted
once. Once cooldown expires, the controller can start a new bounded batch after
reconciling the parked task; it must not spin on the old failed batch.

The next agent must be enabled, installed, capable and not benched/already attempted.
If none qualify, the packet is `parked`. Handoff preserves issue, branch, worktree,
phase, SHA, dirty changes and evidence; the next adapter resumes from that context.
Ledger updates use an advisory file lock and atomic replacement. Use one ledger owner
per host; it is not a distributed lease service. Moonlighter controls cross-host claims.

## Controller integration still required

The helper only computes the transition. Whatever supervises your workers (your own
controller, Paperclip or similar) must do the rest. Item 1 is not precautionary: see
the observed 429-reported-as-success case in [paperclip-adapters.md](paperclip-adapters.md).

1. Capture provider refusal or usage-limit events (including exit 75 from adapters
   with that contract), not generic nonzero exits. Detect JSON-envelope failures even
   when the outer CLI exits 0. Record raw diagnostic evidence privately.
2. Stop dispatch to that account, retain/heartbeat the current Moonlighter claim, and
   inspect the complete process tree. Preserve uncommitted work and prior receipts.
3. Call the helper only after the old writer cannot continue. Verify the worktree's
   current SHA/diff and keep or transfer the coordinator claim through its API.
4. Launch the selected provider's tested adapter, passing identical scope and evidence
   requirements. Do not pass Codex-specific schema flags to Claude, Cursor or Gemini.
5. Reconcile the result with tests and remote state. Authentication problems, missing
   product decisions and failed tests are distinct blockers, not quota failover.

A known pitfall when a supervisor like Paperclip launches workers: GitHub
credentials configured for the whole supervisor process can intercept Git requests
meant for your Gitea server. Test the worker's actual process environment against
Gitea; a `git fetch` from your own shell proving it works is not enough.
