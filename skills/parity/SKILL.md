---
name: parity
description: Prove behavioral equivalence between a pinned oracle and replacement using deterministic BDD runs.
---

# parity

Read the target repository instructions and its trusted `.factory/project.json` from the target branch. Resolve Gitea identity from that configuration and verify it against the Git remote. Installation does not authorize processing existing work. Preserve the scope of the current user request.

Pin the oracle revision and protect its source. Use isolated data stores, matching fixtures and the same scenario IDs on each lane. Run each lane twice at recorded revisions. Normalize only documented nondeterminism; compare observable values, side effects, errors and authorization as required by the crosswalk, not only pass/fail counts.

Export four JSON reports mapping scenario IDs to `{ "status": "passed", "observations": ... }`. Use the factory's `scripts/parity.py oracle-1.json oracle-2.json port-1.json port-2.json`. It rejects empty, red, skipped, nondeterministic or different results. Keep raw reports and the normalization rationale beside revision-bearing receipts. The comparator consumes reports; each repository supplies its BDD runner/exporter.

Equal failures are not passing parity. A changed head requires new evidence. Approved divergences need explicit changed acceptance criteria and crosswalk entries; do not normalize defects away.
