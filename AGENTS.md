# TheGiteaCodeFactory

Read README.md and docs/lifecycle.md for the factory boundaries. Gitea is the
product tracker authority; this repository's GitHub origin is its distribution
remote, not permission to operate other GitHub repositories.

For setup changes read docs/setup.md; for worker/queue changes read docs/moonlighter.md
and docs/coach.md. Preserve the distinction between shipped helpers, source snapshots,
and unverified live integrations. Keep tokens, transcripts, state and environment
files out of Git. Do not start live services, enroll projects or publish releases
as a side effect of editing this kit.

Validate using `bash scripts/check.sh` locally; CI runs `bash scripts/check-ci.sh`,
which omits the Docker Compose parse because the `factory-node` runner image has no
Docker CLI (see docs/setup.md). Moonlighter has its own suite: `php artisan
test` inside `moonlighter/` and `python3 -m pytest moonlighter/tests/Python`.
Change Moonlighter code in its private upstream and bring it over with
`scripts/sync-moonlighter.sh`; only its README, CLAUDE.md, CONTEXT.md,
.env.example and ADR are edited here.
Use isolated fixtures and mock provider/API responses. Record provenance when
updating imported scripts; keep generic defaults separate from host configuration.

## Public documentation

Write for someone who has never seen the author's projects or conversation history.
Define specialized terms or link to docs/glossary.md on first use. Label private
project names, historical issue numbers, machine paths and project-specific policies
as examples; they are never prerequisites. Use neutral owner/project placeholders
and identify the working directory for commands. Keep supported behavior distinct
from plans and observed, version-specific failures. Readers must be able to follow
the main guide from a fresh public clone without access to a private upstream.
