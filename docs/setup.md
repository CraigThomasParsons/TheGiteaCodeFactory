# Gitea and Actions setup

## New standalone installation

Use a dedicated trusted Linux host with Docker Engine and Compose. The checked-in
Compose uses Gitea 1.27.3 and Gitea Runner 4.0.0, persistent named volumes and SQLite.
SQLite keeps this starter independent of application databases. Larger deployments
can migrate storage deliberately rather than sharing an application's database.

```bash
bash scripts/bootstrap.sh
docker compose up -d gitea
docker compose ps
```

Open `http://localhost:3300`, finish Gitea's installer and explicitly create the
administrator account there. The web port is 3300 and SSH is 2223 so the stack can
sit beside an existing Gitea (3000/22) or Paperclip (3100) on the same host. Registration is disabled after setup. Keep the
configured database type/path and external URL consistent with Compose.

For remote workers, change `.env` before starting: set the externally reachable
`GITEA_DOMAIN`, `GITEA_ROOT_URL`, bind address and ports, with HTTPS through your
reverse proxy. `localhost` refers to each worker's own computer, not this server.

In Gitea administration → Actions → Runners, obtain an instance registration token
(or use repository/organization scope for a narrower runner). Put only the token
in `secrets/runner-token` using your editor; do not paste it into terminal history.

```bash
chmod 600 secrets/runner-token
docker compose --profile actions up -d
docker compose logs --tail=50 runner
```

Registration persists in the runner volume. The runner and job containers join
`gitea-code-factory`, so `http://gitea:3000` is reachable from jobs. The runner's
registered instance URL is internal; host workers use the external URL.
The fixed network name supports one starter stack per Docker daemon; change both
Compose and runner config when running a second stack.

Enable Actions in a pilot repository and copy `templates/actions-smoke.yml` to
`.gitea/workflows/factory-smoke.yml`. Commit it through that repository's normal
workflow, dispatch it, and verify a successful job. `factory-node` maps to
`node:22-bookworm` with Git and Bash. Projects needing PHP/.NET or other runtimes
must declare another suitable runner label/image; this image is not a universal
application build environment.

The runner mounts the host Docker socket. Use this on a dedicated trusted runner
host and do not admit untrusted workflow authors. Even with job socket mounting
disabled in the config, it is not a hostile-code isolation boundary.

## Existing Gitea installation

If you already run Gitea, do not stand up a second one to replace it. Keep its data,
URL, repositories and identities. Enable Actions there and register a compatible
runner against its reachable URL using the [official runner instructions](https://docs.gitea.com/runner/installation/docker/).
The supplied Compose is a new-instance recipe; its runner depends on the bundled
Gitea. For an existing instance, use a separate runner deployment and network,
not `compose up` with a guessed URL override.

Configure host workers explicitly:

```bash
export GITEA_SERVER_URL=https://gitea.example.test
export GITEA_TOKEN_FILE="$HOME/.config/gitea-code-factory/token"
```

Create that private token file yourself, readable only by your account. Use a
Gitea token with the repository, issue/review and status permissions needed by the
selected operation. It is distinct from the runner registration token and from
the NightCrew worker token. Agent login remains on the worker host; Compose does
not log in to Codex, Claude, Gemini or Paperclip.

## Sources and version maintenance

The [Gitea Docker guide](https://docs.gitea.com/installation/install-with-docker/)
describes persistent storage and environment configuration. See the
[Gitea 1.27.3 release](https://blog.gitea.com/release-of-1.27.3/) and
[Runner 4.0.0 release](https://blog.gitea.com/release-of-runner-4.0.0/) before changing
pins. Image tags are versioned, not immutable; production deployments should record
verified digests. The runner recipe uses the official image's token-file entrypoint.
