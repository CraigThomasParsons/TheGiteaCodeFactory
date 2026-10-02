# Project onboarding and fleet rollout

Start with a disposable canary. Enroll the rest in batches, tracking every
repository as pending, enabled, blocked, excluded or verified. Inventory all Gitea
projects within the authorized owner/organization scope, including archived ones;
record explicit exclusions rather than silently skipping them.

For each active project:

1. Record canonical Gitea identity, target branch and immutable starting revision.
   Identify existing Moonlighter clients, timers, PR loops and outbound mirrors.
2. Add `.factory/project.json` using `templates/factory-project.example.json`.
   Replace every example: real validation commands/status contexts, assignee,
   feature paths, oracle revision if relevant, providers and merge method.
   This is a trusted instruction contract, not an automatically loaded config in
   every legacy script. Agents read it; each executable's inputs are documented.
3. Install the skill dependency set into an empty destination:

   ```bash
   python3 scripts/install-skills.py --destination /path/to/project/.agents/skills
   ```

   The installer refuses any name collision before copying. For existing personal
   skills, choose a separate project or staging directory and review changes before
   replacing them. Claude users can install into `.claude/skills`, but the shipped
   `pipeline.py` still invokes Codex; it is not a Claude adapter.
4. Add a short project instruction pointing agents to the trusted factory config,
   actual BDD/parity commands and the selected controller. Preserve existing rules.
5. Choose **one** PR controller: the standalone `review:*` skills or Moonlighter's
   `night:*` worker. Register the repository with Moonlighter
   ([how](../moonlighter/README.md#registering-repositories)) if it owns delivery.
6. Configure credentials locally and in Gitea Actions secrets where needed. Copy
   `templates/pr-validation.yml` to `.gitea/workflows/` and replace its placeholder
   with the project's tests; it produces the status check the merge gate waits for.
   Create the review-state labels and enable branch protection with that check
   required (see [pr-loops.md](pr-loops.md#status-checks-the-merge-gate-waits-for)).
7. Run the Actions smoke, then a controlled BDD → implementation → findings → repair
   → independent re-review canary. Verify old head clearance is rejected.
8. Enable `auto_merge` only after the operator has granted that project scope and the
   canary has demonstrated tests, current-revision checks and actual merge evidence.
   Enrollment alone does not instruct a sweep of every existing PR.
9. Add the project to the rollout register with config revision, issue/PR links,
   runner/worker, controller owner, gate evidence and rollback action.

Use a PR for each project's onboarding change. Do not copy another project's tests,
ports, provider choices or oracle database settings. Repeat the canary for each new
runtime family. Archived/read-only projects require an explicit decision before
activation. Disable the old timer/controller before transferring ownership.

## Rollout register fields

`server, repo, base_sha, config_sha, controller, worker, stage, issue_url,
canary_pr_url, tested_head, merged_sha, evidence_paths, blockers, next_action`.

No repositories have been enrolled by creating this starter kit.
