# Features, BDD, TDD and parity

These are different gates in one loop:

| Layer | Question | Output |
|---|---|---|
| Feature description | What should the user observe? | Approved outcomes and acceptance criteria |
| BDD | Can those outcomes be executed as scenarios? | Gherkin, real step bindings, fixture strategy |
| TDD | Does the next implementation change fix a demonstrated behavior? | Failing test → minimal code → passing test → refactor |
| Parity | Does the replacement preserve the oracle's contracted behavior? | Two deterministic runs per lane with matching observations |
| PR gate | Was this exact revision independently reviewed and validated? | Review and test receipts pinned to head/base |

Use `$bdd` before dispatching a slice, `$tdd` in IMPL, and `$parity` for migration
gates. The BDD and parity skills here are new portable extractions of the existing
AMPB migration playbook, not claims that identically named installed skills existed.

## Contract example

```gherkin
@slice-orders @ac-order-1
Feature: Submit an order
  Scenario: Accepted order is visible to its owner
    Given an authenticated customer with an available item
    When the customer submits an order
    Then the response identifies the accepted order
    And the order appears in the customer's history
```

The crosswalk records scenario ID/tag, criterion, oracle entrypoint, port entrypoint,
observable responses and persisted side effects, fixture/seed and test command.
Negative cases (authorization, invalid input, unavailable item) are separate
scenarios with their own criteria. Greenfield projects omit the oracle column with
an explicit reason; BDD still applies.

`skills/dispatcher/scripts/spec-audit.sh` checks feature/crosswalk drift and claimed
tags. It counts Scenario declarations, not expanded examples or executed tests.
Review its output as an audit aid, not proof of coverage.

## Parity execution

Pin a read-only oracle revision. Use isolated databases/ports and deterministic
fixtures for both lanes; do not reseed a live application database. Run the same
scenario corpus twice on the oracle and twice on the port. Save raw logs and
normalized JSON with exact revisions, commands and fixture hashes in adjacent
receipts. Each report has this shape:

```json
{
  "ac-order-1": {
    "status": "passed",
    "observations": {"http_status": 201, "owner_history_count": 1}
  }
}
```

```bash
python3 scripts/parity.py oracle-1.json oracle-2.json port-1.json port-2.json
```

The comparator rejects different scenario sets, unequal observations, nondeterminism,
empty reports and any failed/skipped/missing status. Identical failures are still
failures. It cannot establish that a report came from real execution; the controller
must validate the underlying logs and revision receipts. Each project owns its
actual BDD runner/exporter and justified normalization rules.

A changed head needs new evidence. A copied log with a recent timestamp is not proof.
Approved behavior changes need revised criteria and explicit divergence records;
never hide a regression by stripping the differing field from observations.
