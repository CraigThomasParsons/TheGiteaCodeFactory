# Your first project

This guide uses a fictional `owner/order-service` repository. Substitute your
Gitea account or organization and repository name. No access to the author's
projects or private repositories is required.

The factory is a collection of instructions, scripts and optional services.
It does not automatically connect every component after installation. Start with
one disposable pilot and the standalone PR controller; add the optional
[Moonlighter coordinator](moonlighter.md) after reviewing its integration gaps.
See the [glossary](glossary.md) for BDD, TDD, parity, receipts and other terms.

## 1. Prepare the factory and worker

Clone the public kit:

```bash
git clone https://github.com/CraigThomasParsons/TheGiteaCodeFactory.git
cd TheGiteaCodeFactory
```

Commands below run from this factory checkout unless stated otherwise. You also
need a separate checkout of your pilot project. The worker needs Git, Python 3,
Bash, tmux, an authenticated Codex CLI for the shipped tmux driver, and the
project's build and test tools. Provider credentials belong on the worker.

Follow [Gitea and Actions setup](setup.md) to use an existing Gitea server or
create a new one with Docker Engine and Compose. Complete its Actions smoke test
before continuing. The factory's Docker services do not install or authenticate
the host's agent tools.

## 2. Describe the pilot's configuration

In the pilot checkout, create `.factory/project.json` from
[the project template](../templates/factory-project.example.json). Preserve any
existing configuration. Replace the example server, repository, assignee, branch,
validation command, status contexts and factory revision with your own values.
Record the factory revision using `git rev-parse HEAD` in the factory checkout.
Keep `auto_merge` false during initial review and setup.

The JSON is an instruction contract for agents; legacy scripts do not all load
it automatically. Supply each command's documented inputs explicitly.

From the factory checkout, install the bundled skills into an empty destination:

```bash
python3 scripts/install-skills.py --destination /absolute/path/to/order-service/.agents/skills
```

Replace that absolute path first. The installer refuses name collisions. In the
pilot's agent instructions, point to `.factory/project.json` and document the
real test command. Follow [onboarding](onboarding.md) to install the validation
workflow, create labels and configure branch protection. Replace its deliberately
failing placeholder with your project's actual tests.

## 3. Specify and implement one small behavior

For example: “An authenticated customer can submit an available item as an order
and see it in their history.” Use the [order scenario](testing.md#contract-example)
to write executable behavior-driven development (BDD) scenarios and real step
bindings. Include invalid input and unauthorized access. Map every acceptance
criterion to its scenario and test command in a coverage crosswalk.

Ask your agent to use the installed `$bdd` skill to prepare that contract, then
use `$tmux-pipeline` for one issue with explicit repository, issue and validation
scope. These are skill invocations in the agent client, not shell commands.
Read the [pipeline guide](../skills/tmux-pipeline/SKILL.md) before launching it.
The implementation phase uses test-driven development (TDD): demonstrate a
failing behavior, implement it, then verify it passes.

For a new application, record that parity is not applicable. For a replacement
application, pin the old implementation as an oracle and follow the
[parity procedure](testing.md#parity-execution). Each project must supply its own
runner and observation exporter; the comparison helper does not execute the app.

## 4. Review a PR and prove the gates

Choose the standalone controller in [PR loops](pr-loops.md). Start with
`$pr-review-loop` on your pilot PR, repair findings using `$pr-resolve-loop`, and
request an independent review of the updated commit. Keep the scope to that PR.
Verify that validation passes and that review evidence refers to its current
head. Make a further change and confirm the old evidence no longer permits merge.

After this canary succeeds, explicitly authorize auto-merge for the pilot and
update its policy before using `$pr-review-resolve-loop`. Record the merged commit
and its review and test evidence. A label or a green dashboard alone is not proof.

## 5. Expand deliberately

Use the [rollout register](onboarding.md#rollout-register-fields) to enroll other
repositories in batches, with one PR controller per repository. Coach currently
provides handoff helpers; automatic rate-limit monitoring and relaunch still need
integration. Consult [coach](coach.md) and the [roadmap](roadmap.md).

Once a finite set of issues is complete, follow the
[release guide](releases.md) to verify the cohort, mirror the intended revision to
GitHub and prepare a draft release. Repository enrollment does not authorize
publishing a release. Keep the [operations guide](operations.md) alongside your
deployment notes for recovery and the remaining live acceptance checks.
