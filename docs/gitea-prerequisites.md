# Gitea prerequisites

What an operator must configure on a Gitea server before the factory can run,
beyond the per-project steps in [onboarding.md](onboarding.md). Everything here was
found by enrolling this repository on an existing Gitea 1.26.2 instance on
2026-10-01, not from the Gitea manual. Behaviour may differ on other versions.

## 1. Actions enabled

```ini
[actions]
ENABLED = true
```

Without it no workflow runs, so the merge gate's required status check never
appears and nothing can merge. Restart Gitea after editing `app.ini`.

## 2. A runner, with a label the workflows ask for

`templates/pr-validation.yml` uses `runs-on: factory-node`. A runner must advertise
that exact label or the job stays queued forever — it does not fail, it simply never
starts, which looks like a stuck PR rather than a configuration error.

**The registration token must come from the web UI.** On 1.26.2 the API returns 404
for both `/api/v1/orgs/{org}/actions/runners/registration-token` and the repository
equivalent, with any token scope. Get it from
**Settings → Actions → Runners → Create new Runner**, at site, organization or
repository level depending on how widely the runner should serve.

Registering a standalone runner against an existing Gitea:

```bash
docker run -d --name factory-runner \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v factory-runner-data:/data \
  -e GITEA_INSTANCE_URL=https://gitea.example.com \
  -e GITEA_RUNNER_REGISTRATION_TOKEN=<token from the UI> \
  -e GITEA_RUNNER_NAME=factory-runner \
  -e GITEA_RUNNER_LABELS='factory-node:docker://node:22-bookworm' \
  gitea/act_runner:0.2.13
```

Confirm with `docker logs factory-runner`; `declare successfully` means the label
reached the server. A runner registered with a site-level token is **global** and
will not appear under an organization's runner list, so check the right scope in the
UI before concluding registration failed.

Note `docker-compose.yml` in this repository stands up a *new* Gitea. Do not run it
against a server you already have; register a standalone runner as above instead.

## 3. `factory-node` cannot run this repository's own `check.sh`

`factory-node` maps to `node:22-bookworm`, which has Node 22, Python 3.11 and Git —
but **no Docker CLI**. The last line of `scripts/check.sh` is:

```bash
docker compose --env-file .env.example --profile actions config --quiet
```

That step fails on `factory-node` with `docker: not found`. A project whose
`pr-validation.yml` runs `bash scripts/check.sh` unchanged therefore gets a red
required check for an environment reason, not a code reason.

Pick one:

- run only the language tests in CI and keep the compose validation local;
- give the runner an image that includes the Docker CLI, and declare it under a
  different label, since `factory-node` is documented as Node/Git/Bash only;
- split `check.sh` so the compose check is a separate, optional target.

The same applies to any project whose validation needs a runtime the chosen image
lacks. Match the label to the image, per [setup.md](setup.md).

## 4. API token scopes

For automation that creates repositories, labels and pull requests:

| Need | Scope |
|---|---|
| Create a repository under an **organization** | `write:organization` |
| Create a repository under a **user** | `write:user` |
| Labels, pull requests, merges | `write:repository` |
| Issue and PR comments | `write:issue` |

A token with `write:organization` but not `write:user` returns **403** on
`POST /api/v1/user/repos` while `POST /api/v1/orgs/{org}/repos` succeeds. The error
names the missing scope, so read it rather than assuming the token is invalid.

## 5. Review-state labels, per repository

The seven labels in [pr-loops.md](pr-loops.md) must exist in every enrolled
repository. Creating them over the API:

```bash
while IFS='|' read -r name color desc; do
  curl -s -o /dev/null -w "$name %{http_code}\n" -X POST \
    -H "Authorization: token $GITEA_TOKEN" -H "Content-Type: application/json" \
    -d "{\"name\":\"$name\",\"color\":\"$color\",\"description\":\"$desc\"}" \
    "$GITEA_SERVER_URL/api/v1/repos/$OWNER/$REPO/labels"
done <<'LABELS'
review:requested|0366d6|Ready for an independent review pass
review:in-progress|0e8a16|A reviewer is working on this head
review:findings|d93f0b|Review found issues needing repair
review:resolving|fbca04|A resolver is repairing findings
review:resolved|5319e7|Findings repaired; needs re-review
review:clear|0e8a16|Current head reviewed clear; merge eligible
review:needs-human|b60205|Blocked on a human decision
LABELS
```

## 6. Branch protection

Protect the target branch and mark the validation check required, using the exact
context string Gitea generates — `Project validation / validate (pull_request)` for
the shipped template. A rule that protects the branch without requiring that context
lets the gate's own checks be the only barrier, which is weaker than intended.

## 7. Mirroring to GitHub: SSH is not available

Gitea has **no SSH push-mirror support** ([go-gitea#16437], open since 2021). A
push mirror with an `ssh://` address is rejected with `Invalid mirror protocol`, and
an HTTPS push mirror with no credentials fails with
`could not read Username for 'https://github.com'`. Two workable options:

- **Server-side:** an HTTPS push mirror plus a GitHub fine-grained PAT scoped to the
  single destination repository with Contents: read and write. Mirrors pushes from
  anywhere, at the cost of storing a credential on the Gitea server.
- **Client-side:** give one remote two push URLs, so a single push reaches both and
  no credential is stored:

  ```bash
  git remote set-url --add --push gitea <gitea-url>    # must be re-added explicitly
  git remote set-url --add --push gitea <github-url>
  ```

  Adding any explicit push URL stops the fetch URL being pushed to implicitly, which
  is why the first line is required. This only propagates pushes made from that
  working copy; it is not a server-side mirror.

[go-gitea#16437]: https://github.com/go-gitea/gitea/issues/16437

## Order to work in

1. Enable Actions and restart.
2. Register a runner and confirm its label.
3. Decide the validation command and confirm the runner image can run it.
4. Create the review labels in the pilot repository.
5. Copy `templates/actions-smoke.yml`, dispatch it, confirm a green job.
6. Only then copy `pr-validation.yml` and enable branch protection.

Step 3 is the one most easily skipped and most expensive to skip: a label mismatch
queues forever and a missing runtime fails red, and both look like project faults.
