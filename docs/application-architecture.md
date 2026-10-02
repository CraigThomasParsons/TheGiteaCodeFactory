# Application architecture: CQRS with .NET or Laravel

Projects delivered through the factory may use **.NET** or **Laravel/PHP**.
CQRS is the proposed architecture direction for applications that benefit from
separate read and write models. Choose the runtime per project and record the
decision before dispatching implementation work. These are design profiles, not
bundled application scaffolds or verified runtime adapters.

## What CQRS means

Command Query Responsibility Segregation separates operations that change state
(commands) from operations that retrieve data (queries). For an order service,
`SubmitOrder` validates and records an order, while `GetOrderHistory` returns a
read model shaped for the customer history screen.

Start with separate handlers in one application and one database. CQRS can share
a data store; separate databases and event sourcing are additional decisions.
Microsoft describes both shared-store and separate-store approaches in its
[CQRS pattern guide](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs).

## Two implementation profiles

The following mapping is the factory's proposed convention, not a framework mandate.

| Concern | .NET option | Laravel option |
|---|---|---|
| Entry point | ASP.NET Core endpoint/controller | HTTP controller or Livewire action |
| Command | Explicit command object and application handler | Explicit command object and application handler/action |
| Business rules | Domain code called by the handler | Domain code called by the handler |
| Persistence | Project-selected persistence implementation, such as EF Core | Eloquent or query builder behind the command boundary |
| Query | Query handler returning a purpose-built response | Query class returning a purpose-built response |
| Atomic changes | Transaction owned by the command boundary | Transaction owned by the command boundary |
| Tests | Project-selected .NET test suite and BDD bindings | Project-selected PHP test suite and BDD bindings |

In the Laravel profile, a CQRS command represents application intent; it does not
mean an Artisan console command or necessarily a queued job. Laravel provides
[database transaction support](https://laravel.com/framework/docs/11.x/database#database-transactions);
use documentation matching the version pinned by the project.

Neither profile requires a mediator package. Keep transport, persistence and
business rules distinguishable without adding abstractions that have no purpose.
Queries must enforce authorization as well as commands.

## Record the project decision

Create a repository-local architecture decision record (ADR) documenting:

- Runtime and framework versions, plus actual build, BDD and test commands.
- Which features use CQRS and why; straightforward CRUD may remain simpler.
- Command/query boundaries, validation, authorization and transaction ownership.
- Whether reads observe writes immediately. If projections are asynchronous,
  specify acceptable delay, retry behavior, duplicate handling and recovery.
- Concurrency and idempotency rules, including the observable outcome of retries.

Point project instructions at the ADR so the implementation, architecture and PR
review phases use the same decision. The factory configuration is not a runtime
selector; configure worker dependencies and Actions images for the chosen stack.

## Keep behavior consistent across stacks

Use the same accepted BDD scenarios for either profile. TDD tests the project's
implementation, while parity compares externally observable behavior when replacing
an existing system. Include rejected commands, authorization, concurrent changes
and read-after-write behavior in the contract where applicable.

For example, a successful `SubmitOrder` followed by `GetOrderHistory` must satisfy
the agreed visibility rule in both implementations. A change to eventual consistency
requires an explicit contract decision, not a relaxed parity assertion.

See [testing](testing.md) and [onboarding](onboarding.md) for these gates.
The existing Laravel Moonlighter coordinator remains its own component; choosing
.NET for an application does not select or replace the coordinator's runtime.
