---
name: moonlighter
description: Coordinate factory work through Moonlighter intake and authoritative job claims.
---

# moonlighter

Read the target repository instructions and its trusted `.factory/project.json` from the target branch. Resolve Gitea identity from that configuration and verify it against the Git remote. Installation does not authorize processing existing work. Preserve the scope of the current user request.

Read the factory's Moonlighter guide (`docs/moonlighter.md`) and the deployed coordinator's API/version. Enqueue ready feature issues through authenticated intake; resolve dependencies before execution. Claim exactly one job and retain its claim identity through the local worker pipeline. A local lock complements, but cannot replace, the cross-machine claim.

Report observed progress and revision-bearing receipts. Exit 0 is not completion evidence. Retain/park the claim on quota or uncertain completion; never close the Gitea issue from a process exit alone. Check whether the deployed server supports issue-job requeue before attempting it: the inspected source supported requeue only for PR jobs. Completion requires a verified merged PR and acceptance evidence.

Use exactly one PR controller per repository. Moonlighter's `night:*` state machine and the standalone skills' `review:*` state machine are alternative adapters; explicitly migrate ownership/evidence if switching. Do not run them concurrently against the same PR.
