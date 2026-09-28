---
name: tmux-pipeline
description: Execute one issue in isolated worktrees through implementation, simplification, architecture, review and PR phases.
---

# tmux-pipeline

Read the target repository instructions and its trusted `.factory/project.json` from the target branch. Resolve Gitea identity from that configuration and verify it against the Git remote. Installation does not authorize processing existing work. Preserve the scope of the current user request.

Use fresh worker context for each ordered phase:

1. IMPL: `../tdd/SKILL.md`; one failing behavioral test, minimal implementation, then refactor. BDD and parity are additional required gates when configured.
2. SIMPLIFY: `../simplify/SKILL.md`; preserve behavior and rerun affected checks.
3. ARCHITECTURE: `../improve-codebase-architecture/SKILL.md`; make worthwhile scoped improvements; file larger work separately.
4. REVIEW: `../code-review/SKILL.md`; independent Standards and Spec passes, then fix valid findings and validate.
5. PR: verify pushed head, evidence and issue links, finish title/body, remove draft status. Transfer the PR to the configured review/resolve controller. This worker does not merge.

Read `../supervise-agent-pipeline/SKILL.md` and `../slice-pipeline/references/protocol.md`. Write an immutable prompt containing issue, scope, base/head, expected receipt, prior evidence, commands and forbidden actions. Use a new result path per attempt:

```bash
python3 <skills-root>/slice-pipeline/scripts/pipeline.py phase \
  --phase IMPL --worktree <isolated-worktree> \
  --prompt <packet.txt> --result <private-state>/attempt-1.json
```

Run in a dedicated tmux session and record its session name. The helper is a Codex adapter and holds per-worktree and per-branch locks. Use separate provider adapters for other agents. Check the real process before handoff. Never start another writer against an occupied branch/worktree. A timeout leaves a process requiring reconciliation.

`bash scripts/verify-freshness.sh <worktree> <logs...>` is only a timestamp heuristic. Receipts must also match exact head/base SHAs; timestamp freshness alone cannot establish which code was tested. Create a draft PR on the first scoped implementation commit, push normally, and preserve the same PR through repair attempts.
