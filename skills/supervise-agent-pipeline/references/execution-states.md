# Execution states

Apply the first matching terminal or active condition:

1. `BLOCKED_SCOPE`: observed mutation or requested action exceeds the grant.
2. `BLOCKED_GATE`: a declared product, test, build, or review gate failed.
3. `WAITING_APPROVAL`: a human decision is required or the requested action is not pre-authorized.
4. `WAITING_PROVIDER`: the executor is unavailable because of quota, rate limit, authentication, or provider outage and an allowed fallback may exist.
5. `WORKING`: the worker or its subagents are active.
6. `DONE`: a receipt exists, validates, and satisfies the phase evidence contract.
7. `FAILED_INFRASTRUCTURE`: the process died, the adapter is unavailable, or prior success is ambiguous.
8. `STALLED`: the live process was idle without a receipt for two consecutive observations.
9. `IDLE`: first live idle observation without a receipt.

Never convert provider failure into gate failure. Never convert worker exit success into `DONE` without a validated receipt.
