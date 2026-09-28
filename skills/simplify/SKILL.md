---
name: simplify
description: Simplify an issue's changed code without changing behavior, then verify and push the scoped cleanup. Use for the SIMPLIFY phase of slice-pipeline or an explicit code-simplification request.
---
# Simplify

This implements the SIMPLIFY phase of the tmux pipeline (see `../tmux-pipeline/SKILL.md`). It is a standalone skill, independent of any agent's built-in simplify command.

Read the issue, base SHA, diff, tests and prior phase receipt. Remove avoidable duplication, unnecessary branches, misleading names and speculative scaffolding within the changed code. Keep public behavior, contracts and approved architecture unchanged. Prefer fewer concepts over extra helper layers. Do not widen this into a repository-wide cleanup or architectural redesign; architecture has its own following phase.

Verify affected tests and required checks; commit and push nonempty worthwhile changes. A no-change result is valid. Record edits, evidence, head SHA and any issue-linked deferrals in the phase receipt, then stop. Never merge or enable auto-merge.
