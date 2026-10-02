# Factory lifecycle

## The outcome

Keep delivering a deliberately queued body of features over days or weeks,
with executable behavior evidence at every transition. A review-ready PR is
intermediate progress. A feature is complete when its accepted behavior is
proven on merged code. A release is a separate, finite milestone.

## Application architecture

Choose the project runtime and record its architecture before implementation.
The [CQRS guide](application-architecture.md) describes .NET and Laravel options
and how both use the same BDD, TDD and parity gates.

## Ownership

| Concern | Authority |
|---|---|
| Feature intent and approved changes | Feature spec and linked Gitea issues |
| Behavior contract | BDD scenarios, acceptance crosswalk, pinned oracle when applicable |
| Issue/PR history and merged code | Gitea |
| Which computer owns a job | Moonlighter's atomic claim |
| Which local process writes a branch | Worker process plus branch/worktree lock |
| Agent availability | Coach observations, account cooldown and configured capabilities |
| Worker execution | Repository-local adapter / tmux pipeline |
| Merge decision | One configured PR controller plus Gitea branch protection |
| Released revision and assets | Release manifest, matching GitHub refs and draft release |

Paperclip can supervise agent runs; it must consume the same claim and receipts,
not create an independent task queue that races the coordinator. Gitea Actions runs
validation/advisory review; it is not the long-lived agent supervisor.

## Gates

1. **Specify:** capture user outcomes, constraints, failure behavior and criteria.
2. **Contract:** create executable BDD, real step bindings and coverage crosswalk.
   A migration requires a pinned, green, deterministic oracle; greenfield projects
   explicitly mark parity not applicable.
3. **Queue:** create/reuse issues and dependencies; mark ready only after prerequisite
   evidence exists. Record a stable release cohort rather than a forever-growing queue.
4. **Claim:** the coordinator assigns one job to one eligible worker. Keep one serial writer
   per branch even when there are many worker computers.
5. **Implement:** IMPL → SIMPLIFY → ARCHITECTURE → REVIEW → PR, each with fresh context,
   same issue, isolated worktree and immutable attempt evidence. TDD guides implementation;
   BDD and parity validate the feature contract.
6. **Review/repair:** independent current-head Standards and Spec reviews; fix findings,
   run required checks, push and re-review. Three rounds by default, then park.
7. **Merge/reconcile:** only the merge controller merges. Verify the actual merge SHA
   and acceptance criteria before closing a feature or completing its job.
8. **Release:** once every issue in the selected cohort is accounted for, validate the
   release revision, mirror explicit refs to GitHub and prepare a draft release.

## Durable evidence and failure handling

Every attempt records issue/job/claim, repository, base/head, branch/worktree,
phase/provider/account, allowed paths, acceptance criteria, exact commands,
exit codes and log paths. Store secrets and private receipts outside the checkout.
New commits invalidate prior clearance. Local state is reconstructible from tracker
links and preserved receipts, but it cannot replace the coordinator claim.

Exit 0 does not mean accepted work. Exit 75 can indicate provider exhaustion only
where the adapter implements that contract. On a rate limit, bench the account,
confirm the old writer stopped, preserve dirty work and route the same phase.
On failed tests, unresolved requirements, unavailable credentials or unknown writer
ownership, park with a reason and retry condition. Continue other independent jobs.

An empty ready queue can mean dependencies, cooldown or human blockers. It is not
proof that all issues are complete. Recurring maintenance jobs never permanently
complete and are excluded from the finite release cohort.
