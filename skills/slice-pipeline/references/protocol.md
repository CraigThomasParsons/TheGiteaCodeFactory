# Durable phase protocol

The helper is a Codex orchestration adapter, not a proof verifier or security sandbox.
Each project uses its own private state directory and one supervisor lock. The first start requires `--workspace`; later starts resume the recorded workspace. `status` exposes session and latest tick result. Preserve queue/attempt history.

Each tick re-observes tracker/claim state and takes at most one orchestration action. Fresh `codex exec` workers implement only their assigned phase. The driver waits between ticks and stops on awaiting_review, blocked, or complete. It uses a 20-minute execution timeout; a timed-out process may still be live and requires reconciliation before restart. The operator must give long-running supervisors an operating window and stop/reconcile them at its boundary.

A phase receipt contains issue_url, phase, base_sha, head_sha, changed_files, scope_statement, validation (command, exit_code, evidence_path), push_status, pr_url, discovered_issue_urls, blockers, status, next_phase. The wrapper records CLI exit separately. Check all semantics against actual Git, tests and remote state; JSON schema validation only establishes shape.

Do not force-push, delete branches, edit oracle source, deploy, or merge from delivery workers. The separate PR controller owns merging under explicit project policy. Empty validation is never green. Record occupied branch locks and process identity. On provider limits use the coach workflow; no automatic retry across accounts without a configured provider adapter.

A slice completes only after its required acceptance criteria are evidenced by merged work. Archive completed queues and continue with the next dependency-ready slice when the invocation authorizes it. A release uses a finite issue-set snapshot, not the momentary absence of queued jobs.
