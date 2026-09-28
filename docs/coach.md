# Coach: bench, checkpoint, hand off

## What was found

`http://localhost:3100/` identifies itself as **Paperclip** (observed 2026-09-28).
The operator reports that the coach never worked. A separate prototype,
`AgileMedievalCodexBoard/ai_tools/night-crew/crew-coach.ts`, routes by capability and
account availability evidence. That source is conceptual provenance, not a verified
Paperclip integration. Its raw vendor commands are not interchangeable JSON adapters.

The required behavior is: **observe rate limit → bench that account → preserve the
same task → hand off to the next eligible agent**. A failure is not task completion.

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
per host; it is not a distributed lease service. NightCrew controls cross-host claims.

Paperclip has since been installed and exercised on one host; see
[paperclip-adapters.md](paperclip-adapters.md). Two results bear directly on the
requirements below: Paperclip ships no rate-limit failover of its own, and a run whose
provider call was refused with HTTP 429 still reported `Status: succeeded`. Item 1 below
is therefore confirmed necessary, not precautionary.

## Controller / Paperclip integration still required

1. Capture provider refusal or usage-limit events (including exit 75 from adapters
   with that contract), not generic nonzero exits. Detect JSON-envelope failures even
   when the outer CLI exits 0. Record raw diagnostic evidence privately.
2. Stop dispatch to that account, retain/heartbeat the current NightCrew claim, and
   inspect the complete process tree. Preserve uncommitted work and prior receipts.
3. Call the helper only after the old writer cannot continue. Verify the worktree's
   current SHA/diff and keep or transfer the coordinator claim through its API.
4. Launch the selected provider's tested adapter, passing identical scope and evidence
   requirements. Do not pass Codex-specific schema flags to Claude, Cursor or Gemini.
5. Reconcile the result with tests and remote state. Authentication problems, missing
   product decisions and failed tests are distinct blockers, not quota failover.

The handoff reports a Paperclip Git-auth conflict caused by company-wide GitHub
credentials intercepting the Gitea bridge. A new integration must test its actual
process environment and local Gitea credentials; a shell `git fetch` alone is insufficient.
The report describes a successful canary, but this repository has not independently
rerun it. No Paperclip settings were changed while preparing this kit.
