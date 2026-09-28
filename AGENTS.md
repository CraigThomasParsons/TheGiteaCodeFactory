# TheGiteaCodeFactory

Read README.md and docs/lifecycle.md for the factory boundaries. Gitea is the
product tracker authority; this repository's GitHub origin is its distribution
remote, not permission to operate other GitHub repositories.

For setup changes read docs/setup.md; for worker/queue changes read docs/nightcrew.md
and docs/coach.md. Preserve the distinction between shipped helpers, source snapshots,
and unverified live integrations. Keep tokens, transcripts, state and environment
files out of Git. Do not start live services, enroll projects or publish releases
as a side effect of editing this kit.

Validate using `bash scripts/check.sh`; imported NightCrew tests additionally use
`python3 -m pytest integrations/nightcrew/tests/Python/test_gitea_night.py`.
Use isolated fixtures and mock provider/API responses. Record provenance when
updating imported scripts; keep generic defaults separate from host configuration.
