---
name: improve-codebase-architecture
description: Find architectural friction in a change set, evaluate module depth and test boundaries, and apply worthwhile scoped refactors in a pipeline architecture phase. Also supports standalone architecture exploration.
---
# Improve codebase architecture

Adapted from the operator's original The-Pulse supporting skill. Read CONTEXT.md and applicable ADRs before suggesting changes; preserve the domain vocabulary and existing decisions.

Use this vocabulary: a **module** hides implementation behind an **interface**; **depth** is useful hidden complexity relative to interface complexity; a **seam** is an observable test boundary; an **adapter** connects external infrastructure; **locality** keeps related concepts together; **leverage** is the amount of useful behavior improved by a small interface change. Avoid extracting functions solely to expose internals to tests. One adapter often represents a hypothetical seam; multiple real consumers provide stronger evidence for abstraction.

1. Scope the scan to the issue's change set and closely affected modules. For standalone exploration, use the user's direction or recently changing areas. Identify shallow interfaces, knowledge spread across files, leaking boundaries, and behavior that is hard to test through the public interface.
2. Apply the deletion test: would removing the proposed abstraction concentrate complexity, or merely move it? Prefer designs that hide meaningful complexity and keep related behavior together. Respect ADRs; don't implement a conflicting design without an explicit decision.
3. For each candidate record files, observed problem, proposed change, public interface/test effects, and strength (Strong / Worth exploring / Speculative). Separate measured friction from hypothetical future needs.
4. In slice-pipeline ARCHITECTURE mode, apply the worthwhile candidates that fit the issue's scope. Keep behavior unchanged, validate it, commit and push each refactor. Record too-large candidates with a rationale and assigned follow-up issue. Do not stop at an assessment and do not enter REVIEW in this context. No candidate is a valid result when the current design needs no change; do not manufacture edits.
5. In standalone exploration mode, present candidate before/after diagrams when useful and ask which substantial direction to explore before implementing a new design. Use a temporary HTML report only when it helps the user compare candidates; [references/HTML-REPORT.md](references/HTML-REPORT.md) provides the original report patterns. Do not automatically open a browser from an unattended worker. Record newly agreed domain terms and lasting decisions in the repository's domain/ADR documents within the authorized scope.

Pipeline packets already define the scope; no repeated design-selection interview is needed for ordinary behavior-preserving improvements. Decisions that change product behavior or approved architecture remain the operator's.
