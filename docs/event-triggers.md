# Event-driven PR review triggers

The standalone review loop ([pr-loops.md](pr-loops.md)) normally starts when you ask
your agent or when a timer fires. This page adds an event path: when a pull request
(PR; see [glossary.md](glossary.md)) is opened, gets a new commit, is reopened or is
labelled for review, a small Gitea Actions job tells the worker computer about it so
the review loop can pick it up straight away.

Commands on this page run from the root of your cloned **TheGiteaCodeFactory**
repository unless a step says otherwise. Replace `owner/project` and the example
hostname with your own.

## What is in this kit and what is not

| Piece | Where it comes from | Status |
|---|---|---|
| `templates/pr-review-trigger.yml`, the workflow you copy into each project | This kit | Shipped; its job condition and step are covered by `tests/test_event_trigger.py` |
| `scripts/setup-host-runner.sh` and `templates/host-runner/`, which set up the `factory-host` runner | This kit | Shipped; tested against fake `gitea-runner` and `systemctl` programs |
| `pr-trigger`, the command the job calls, plus the queue it writes and the systemd path unit that drains that queue into the review loop | The PR loop's own repository, installed to `$HOME/.local/bin/pr-trigger` on the worker | **Not in this kit.** Install it from the PR loop before enabling the workflow |
| End-to-end run on a live Gitea server | — | Not yet verified by this kit; see [roadmap.md](roadmap.md#1-prove-the-review-loop-live) |

The job does not run the review itself. It hands four facts (repository, PR number,
head commit and event) to `pr-trigger`, which records them and returns. The review
loop then re-reads the PR from Gitea before acting, so a dropped or duplicated
trigger costs a delay, not a wrong decision.

## How it fits together

1. Gitea fires a `pull_request_target` event for a PR into `develop`.
   `pull_request_target` runs the workflow file **from the target branch**, not from
   the PR, so a PR cannot change what the job does.
2. The job's condition skips drafts, PRs from forks and label changes other than
   `review:requested` and `review:findings`.
3. The job runs on a runner labelled `factory-host`. That runner is in **host mode**:
   jobs run as a normal process of the worker's user account, with no container, so
   they can reach `$HOME/.local/bin/pr-trigger`.
4. The step calls
   `"$HOME/.local/bin/pr-trigger" --repo owner/project --pr N --sha HEAD --event E`
   and adds `--label L` only when Gitea sent a label name.

## Which events fire

| Gitea action | Fires when | Notes |
|---|---|---|
| `opened`, `reopened` | Always (non-draft, same repository) | |
| `synchronize` or `synchronized` | Always | A new head commit. Gitea may spell it `synchronized` in the event payload |
| `labeled` or `label_updated` | Label is `review:requested` or `review:findings`, or the label name is empty | Gitea may report `label_updated` and may leave the label name empty; `pr-trigger` then records the label as `unknown` and the loop reads the real labels from Gitea |

Removing a label, closing a PR and `review:clean` (the label for a clean
current-head review) do not fire. The workflow's `types:` list uses the GitHub
names (`synchronize`, `labeled`); the spellings above describe what may arrive in
`github.event.action`, which is why the condition does not filter on action names
except to recognise label events.

`pr-trigger`'s contract, owned by the PR loop: exit 0 when the event was accepted or
deliberately ignored, 2 for bad arguments, 3 for misconfiguration or a failed write.
A non-zero exit fails the job, so problems show up in the PR's Actions tab.

## Set up the `factory-host` runner (once per worker)

You need: a worker computer where the review loop runs, `gitea-runner` (Gitea's
Actions runner, version 4.1.0 was used to check the options below) on `PATH` or at a
known path, a systemd user session, and `pr-trigger` installed by the PR loop.

1. In Gitea, go to **Site Administration → Actions → Runners → Create new Runner**
   and copy the registration token. A site-level token makes a **global** runner that
   can serve every repository; use an organization or repository token for a
   narrower one ([details](gitea-prerequisites.md#2-a-runner-with-a-label-the-workflows-ask-for)).
2. Save only the token into a private file with your editor, not on a command line,
   then restrict it:

   ```bash
   mkdir -p -m 700 "$HOME/.config/factory-host-runner"
   # paste the token into this file with your editor, then:
   chmod 600 "$HOME/.config/factory-host-runner/registration-token"
   ```

3. Render the runner config and systemd user unit, register, enable and check:

   ```bash
   bash scripts/setup-host-runner.sh render
   bash scripts/setup-host-runner.sh register \
     --instance https://gitea.example.com \
     --token-file "$HOME/.config/factory-host-runner/registration-token"
   bash scripts/setup-host-runner.sh enable
   bash scripts/setup-host-runner.sh doctor
   ```

   Add `--dry-run` to `render`, `register` or `enable` to see what would change
   first. Add `--runner-bin PATH` if `gitea-runner` is not on `PATH`, and
   `--name NAME` to choose the runner's name (default `factory-host-<hostname>`).

4. Delete the registration token file once `doctor` reports the runner registered;
   the runner keeps its own credentials in its `.runner` file.

What the script does:

- `render` writes `$HOME/.config/factory-host-runner/config.yaml` (mode 600) and
  `$HOME/.config/systemd/user/gitea-runner-factory-host.service`, and creates the
  state folder `$HOME/.local/state/factory-host-runner` (mode 700). It honours
  `XDG_CONFIG_HOME` and `XDG_STATE_HOME`. Files whose content already matches are
  left untouched; changed files are replaced.
- `register` runs `gitea-runner register` once with the label `factory-host:host`.
  It refuses a token file that is not owned by you or is readable by others, passes
  the token with `--token-file` (or the `GITEA_RUNNER_REGISTRATION_TOKEN`
  environment variable on runners without that option, never as a command-line
  argument), redacts the token from the runner's output and sets the resulting
  `.runner` file to mode 600. If `.runner` already exists it only fixes that file's
  mode; to re-register, delete the runner in Gitea and the `.runner` file.
- `enable` runs `systemctl --user daemon-reload` and
  `systemctl --user enable --now gitea-runner-factory-host.service`. A user service
  stops when you log out unless lingering is on; the script tells you when it is
  off, and `loginctl enable-linger <user>` turns it on.
- `doctor` changes nothing. It checks the runner binary, how it accepts the token,
  the config label, the `.runner` file and its mode, the unit, whether the service
  is enabled and active, lingering, and that `$HOME/.local/bin/pr-trigger` exists.
  It exits 3 if anything needs fixing.

Exit status for every command: 0 done or nothing to do, 2 bad arguments, 3
misconfiguration or a failed write.

The runner advertises only `factory-host`. Other runners on the same computer keep
their own names, labels and config; this script does not read or change them.

## Enable the trigger in a project

In the project's repository (not the factory checkout), add the template on the
`develop` branch through the project's normal PR workflow:

```bash
mkdir -p .gitea/workflows
cp /path/to/TheGiteaCodeFactory/templates/pr-review-trigger.yml .gitea/workflows/
```

Because it uses `pull_request_target`, Gitea reads the workflow from `develop`. It
has no effect until it is merged there, and a PR that edits it cannot change how it
runs for that PR. If the project's integration branch is not `develop`, change
`branches:` to match.

Make sure the `review:requested` and `review:findings` labels exist in the project
([labels](gitea-prerequisites.md#5-review-state-labels-per-repository)).

The first line, `# pr-review-trigger template v1`, identifies the template version.
Compare it with this kit's copy when updating.

## Security notes

- Host mode is not an isolation boundary: a job on `factory-host` runs with the
  worker account's files and credentials. Only the shipped trigger workflow should
  target that label. Restrict who can push workflow files to the target branch.
- The trigger checks out nothing, uses no `uses:` actions and no secrets, and passes
  event fields through environment variables rather than splicing them into the
  shell script, so a crafted label or branch name stays one argument.
- Fork PRs are skipped because the fork's contents are not trusted; review them by
  the manual path in [pr-loops.md](pr-loops.md).
- Keep the registration token, the runner's `.runner` file and its config out of
  Git. The setup script writes them under `$HOME`, outside any checkout.

## Concurrency

The workflow groups runs by repository and PR number with
`cancel-in-progress: false`: a running trigger finishes, and a newer pending run for
the same PR may replace an older pending one. That is safe because the loop re-reads
the PR. Whether `concurrency` is honoured depends on your Gitea version; without it,
duplicate triggers are absorbed by `pr-trigger` and the loop.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Trigger job stays queued | No online runner advertises `factory-host`. Run `bash scripts/setup-host-runner.sh doctor` on the worker |
| Job fails with "No such file or directory" for `pr-trigger` | `pr-trigger` is not installed in the runner account's `$HOME/.local/bin` |
| Job fails with exit 3 | `pr-trigger` reported misconfiguration or could not write its queue; see the job log and the PR loop's documentation |
| Nothing happens on a PR | It is a draft, comes from a fork, targets another branch, or the workflow is not yet on `develop` |
