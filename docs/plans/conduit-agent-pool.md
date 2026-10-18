# Conduit Agent Pool Plan

Status: proposed  
Owner: TheGiteaCodeFactory  
Control plane consumer: AMPB  
Related work: [pull-based worker pool #2](https://github.com/CraigThomasParsons/TheGiteaCodeFactory/issues/2), [agent-pool-core convergence plan](https://github.com/CraigThomasParsons/PR-Review-Resolver-Loop-Merge-Gitea-Github/issues/5), [AMPB Agent and Human boards #24](https://github.com/CraigThomasParsons/AgileMedievalPeasantBoard/issues/24)

## Goal

Extend `agent-pool-core` with database-configured **Conduits**: durable, named
agent identities that combine a provider, model-selection policy, capabilities,
skills, permissions and optional personality. Distributed worker machines
register independently, advertise which Conduits they can host and pull only
jobs for which the Conduit is eligible.

TheGiteaCodeFactory owns the execution model. AMPB presents an authenticated
control panel for configuring and observing it. Neither AMPB nor a browser
stores provider credentials.

## Architectural boundary

| Component | Owns |
|---|---|
| TheGiteaCodeFactory / agent-pool-core | Conduits, providers, model policies, capabilities, skills, matching, claims, leases, epochs, receipts and execution |
| AMPB API | Authenticated management commands, human authorization, audit integration and projections consumed by its control panel |
| AMPB BFFM | Browser sessions, frontend-specific aggregation and authorized real-time updates |
| Worker installation | Provider CLI/login, local secret material, worktrees, runtime health and execution |
| Gitea | Repositories, issues, pull requests, labels, checks and merge state |

The source of truth must be unambiguous. Factory execution state belongs to
agent-pool-core. AMPB may store projections and management audit records, but it
must not grow a second scheduler or lease implementation.

## Vocabulary

- **Provider**: an external agent runtime such as Claude, Codex or Grok.
- **Model policy**: fixed model, approved set or provider-controlled `auto`.
- **Conduit**: a named operational identity such as Charlie or Chase.
- **Capability**: a responsibility the Conduit may assume, such as planning,
  coding, reviewing, resolving or testing.
- **Skill**: a versioned procedure or knowledge package available to the
  Conduit, such as BDD, TDD or code review.
- **Permission**: an action the Conduit is authorized to publish.
- **Worker**: a machine/process capable of hosting one or more Conduits.
- **Network**: the physical or logical location of workers.
- **Personality**: optional communication and working-style instructions; never
  an authorization mechanism.
- **Lease**: a time-limited job claim issued to one Conduit on one worker.
- **Epoch**: a monotonically increasing fencing token for a job claim.

## Example seed configuration

### Charlie

- Provider: Claude
- Model policy: `auto`
- Capabilities: planning, reviewing
- Permissions: publish plans and reviews
- Restrictions: cannot code, merge or review his own authored implementation

### Chase

- Provider: Claude
- Model policy: fixed Sonnet
- Capabilities: coding
- Skills: TDD and repository-specific coding standards
- Permissions: create branches, commits and implementation PRs
- Restrictions: cannot approve, merge, release or change job priority

### Grok-bot

- Provider: Grok
- Initial capabilities: explicitly configured, deny by default
- Later personality: exploratory and unconventional, but bound by the same
  permissions, evidence requirements and lease fencing as every Conduit

## Data model

Suggested logical records; adapt naming to the implementation language and
existing agent-pool schema.

- `providers`: key, adapter, enabled, health policy.
- `model_policies`: provider, mode (`fixed`, `allow_list`, `auto`),
  requested model and approved actual models.
- `conduits`: name, provider, model policy, enabled, concurrency limit, trust
  level and optional personality profile.
- `capabilities`: stable keys such as `planning`, `coding`, `reviewing`.
- `conduit_capabilities`: grants and restrictions.
- `skills`: key, version, source, integrity identifier and evidence contract.
- `conduit_skills`: enabled skill versions.
- `permissions`: command/publication permissions.
- `conduit_permissions`: explicit grants; deny by default.
- `networks`: operator-defined location identifier and enabled state.
- `workers`: stable identity, network, status, heartbeat and capacity.
- `worker_conduits`: which Conduits a worker can host and their availability.
- `jobs`: required capability/skills, repository policy, affinity and
  separation-of-powers constraints.
- `leases`: job, Conduit, worker, epoch, issued/expiry times and status.
- `attempt_receipts`: requested/actual provider and model, commit/head,
  commands, evidence, timestamps and deterministic failure classification.
- `personality_profiles`: versioned prompt fragment and presentation metadata.

Store no provider tokens or login material in these records. Persist only an
opaque secret reference when necessary; resolve it on the authorized worker.

## Pull and matching protocol

1. A worker authenticates outbound to the factory.
2. It reports runtime health and the Conduits it can currently host.
3. A hosted Conduit requests eligible work.
4. The server filters jobs by capability, skill version, permission, repository
   policy, provider/model health, worker capacity, network policy and
   separation of powers.
5. The server atomically grants one lease with a new epoch.
6. Heartbeats renew only the current epoch.
7. Checkpoints and final receipts include job, lease, epoch, Conduit, worker,
   requested model and actual model.
8. Stale epochs are rejected from heartbeat, checkpoint, label, review, merge
   and completion operations.
9. On timeout or deterministic provider failure, the doctor releases or
   quarantines the attempt and makes the job eligible for another compatible
   Conduit without accepting duplicate results.

Workers initiate outbound connections. They do not require public IP addresses,
DDNS or inbound connectivity, and they do not communicate directly with workers
on other networks.

## Separation of powers

Represent these as data-backed policies rather than personality instructions.

- An implementation author cannot supply the independent approval for the same
  revision.
- A reviewer cannot merge merely because it reviewed.
- A planner cannot silently expand acceptance criteria during implementation.
- A resolver can change code only for recorded findings.
- Publishing and releasing remain separately authorized.
- Human-only commands include disabling a Conduit, changing trust, granting
  capabilities and overriding a quarantined job.

## AMPB Conduit control panel

AMPB should consume authenticated factory-management APIs and project them into
the Human Board. The first version is Craig-only.

Required views:

- Conduit list with provider, model policy, capabilities, skills, permissions
  and enabled state.
- Worker/network presence, health, last heartbeat and hosted Conduits.
- Active leases, epochs, expiry and current phase.
- Provider/model availability and doctor classification.
- Recent receipts, evidence links and rejected stale submissions.
- Audit history for every configuration change.

Required commands:

- Create, edit, enable and disable a Conduit.
- Assign capabilities, skills and permissions.
- Select fixed, allow-listed or `auto` model policy.
- Set concurrency and repository/network restrictions.
- Attach or version a personality profile.
- Drain a Conduit without killing current work.
- Revoke a worker or Conduit identity.

The UI must never accept or reveal raw provider credentials.

## Personality phase

Personality is deliberately deferred until matching, authorization and
receipts are proven. A personality profile may affect tone, explanation style,
risk posture and preferred problem-solving approach. It must not grant
capabilities, bypass evidence, select unapproved models or weaken
separation-of-powers policy.

Version personality profiles and record the version used in each attempt
receipt so behaviour can be reproduced and audited.

## Delivery phases

### Phase 0 — prerequisite convergence

Complete the single-repository `agent-pool-core` pilot described in the
convergence issue. Do not build Conduits on dormant competing pools.

### Phase 1 — contracts and migrations

- Define provider, model policy, Conduit, capability, skill, permission, worker,
  lease and receipt schemas.
- Write invariants and Gherkin scenarios.
- Seed Charlie and Chase examples without credentials.
- Preserve compatibility with the existing single-provider pilot.

### Phase 2 — database-backed matching

- Replace environment-only eligibility with database-backed Conduit matching.
- Implement fixed, allow-list and `auto` model policies.
- Require actual-model reporting and reject disallowed downgrades.
- Enforce capability, skill and separation-of-powers rules.

### Phase 3 — distributed worker registration

- Add worker identities, outbound registration, health advertisement and
  hosted-Conduit availability.
- Prove workers on two networks can pull from the same authority without inbound
  ports.
- Add drain, revoke, heartbeat and capacity behaviour.

### Phase 4 — AMPB management API and control panel

- Add authenticated management commands and projections.
- Build the Craig-only Conduit control panel.
- Publish authorized BFFM/Reverb updates.
- Add audit history and explicit confirmations for destructive changes.

### Phase 5 — personalities

- Add versioned personality profiles.
- Pilot one non-authoritative personality difference.
- Verify permissions and evidence remain identical with personality enabled.

## First vertical slice

Create Charlie and Chase from seed data. Register one worker. Queue one coding
job requiring the coding capability and TDD skill. Prove:

1. Charlie cannot claim it.
2. Chase can claim it using the configured Sonnet policy.
3. the lease contains an epoch;
4. the attempt reports the actual model;
5. Charlie may independently review Chase's resulting revision;
6. Chase cannot approve his own work;
7. the Human Board shows both identities, lease and evidence; and
8. disabling Chase prevents new claims without corrupting the active receipt.

## Acceptance criteria

- Conduits are durable database records, not hard-coded shell identities.
- Provider, model policy, capability, skill, permission, worker and personality
  are independently configurable.
- Matching is deny by default and performed before a lease is granted.
- Workers on different networks can participate using outbound authenticated
  connections only.
- Only the current lease epoch can mutate job state or publish results.
- Requested and actual models are recorded; unapproved downgrades are rejected.
- Separation of powers is enforced by server-side policy.
- AMPB can manage Conduits without becoming a second scheduler.
- No raw credential appears in the database, APIs, UI, logs or receipts.
- Personalities cannot alter permissions or evidence requirements.
- Existing single-provider execution remains available as a rollback path until
  the Conduit pool passes its live canary.

## Non-goals for the first release

- Offline multi-master scheduling or conflict reconciliation.
- Direct worker-to-worker communication.
- Autonomous permission changes.
- Personality-driven authorization.
- Storing provider credentials in AMPB.
- Migrating every repository before one canary is proven.
- Removing the legacy execution path before rollback is demonstrated.

## Handoff instructions

An implementation agent should begin by reading the related convergence issue
and current `agent-pool-core` schema. It must update this plan when code reality
differs, produce one feature slice per phase, use the repository's BDD-to-slice
pipeline, and attach reproducible evidence to the canonical issue. Do not claim
the distributed or AMPB phases complete from unit tests alone; each requires a
live canary at its stated boundary.
