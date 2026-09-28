# Operations, recovery and validation

## Run and resume

Start with one repository and one active writer. Keep the factory checkout at a
reviewed commit; record that SHA in project configuration and receipts. Install the
skills on each worker and use explicit paths. Codex noninteractive workers use
structured output, described in the [official guide](https://developers.openai.com/blog/eval-skills).
A JSON schema establishes response shape, not completion.

`pipeline.py start` creates a detached tmux supervisor; `status` reports its session.
Use the documented `--state` per repository. The driver can run for an extended
period, but it is not a reboot-resilient service and does not supply a finite overall
deadline; the operator's supervising service must enforce its operating window and
reconcile surviving workers at shutdown. Use NightCrew scheduling where available.

On restart inspect the claim, recorded process, branch lock, attempt outputs,
Git state and remote PR before retry. Never delete a lock file solely because a
heartbeat is stale. A dead process releases an advisory lock, but a coordinator
claim still needs reconciliation. Preserve uncommitted changes and prior attempts.

## Stop and rollback

- Stop new intake/claims first, then let the active bounded phase finish or checkpoint.
- Disable the project's owning timer/controller to pause the fleet lane. Do not run
  two loops as an attempted recovery.
- Revert a project's onboarding PR to remove the workflow/config; preserve logs and
  evidence. Restore the previous skill version from its reviewed source.
- `docker compose --profile actions stop` stops this starter's services without
  deleting volumes. `down` retains named volumes unless `--volumes` is passed.
- Back up Gitea `/data` (database, repositories, configuration, keys) using the
  [official backup procedure](https://docs.gitea.com/administration/backup-and-restore/)
  before upgrades. Quiesce writes for consistent SQLite backups and test restoration
  in a separate stack. Runner registration state is separate from repository data.

## Credential boundaries

`.env`, `secrets/`, state, logs and tokens are ignored. Credentials are not copied
from local services. Gitea PAT, runner registration token, NightCrew token, provider
login and GitHub release credentials have different roles. Configure them explicitly
per host/service and test that exact process environment. Use TLS for remote secrets.
Never commit provider transcripts that may contain credentials or private diff content.

The deterministic merge helper refuses API redirects. The receipt directory must
be privately owned; project source must not be able to substitute controller receipts.
Operator-configured commands and agent tools still have real host permissions.

## Checks provided

```bash
bash scripts/check.sh
```

Runs portable helper tests, imported merge-gate tests, phase-driver tests, reviewer
unit tests, Python/shell syntax checks and Compose rendering. Does not invoke
providers, start Docker services, claim jobs, write to Gitea or publish to GitHub.
Tests of NightCrew's imported Python worker require pytest and are run separately:

```bash
python3 -m pytest integrations/nightcrew/tests/Python/test_gitea_night.py
```

Live acceptance still requires: fresh server installation and runner registration;
Actions canary; one real reviewed/repaired PR; stale-head rejection; quota handoff
with the old writer gone; coordinator restart/claim recovery; and a GitHub draft
release from a finite completed cohort. Record each tested revision and result.
