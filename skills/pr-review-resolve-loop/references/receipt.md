# Clean-review receipt

Write atomically under `~/.local/state/gitea-pr-review-resolve/<owner>-<repo>/<pr>/receipt.json` after checking both independent review reports and actual validation outputs. The directory and receipt must belong to the current OS user and not be writable by other users. Never read a receipt from PR-controlled source files. Retain supporting reports and logs in the same private controller state directory.

```json
{
  "schema_version": 1,
  "server": "https://gitea.example.test",
  "repo": "OWNER/REPO",
  "pr": 123,
  "head_sha": "full reviewed head SHA",
  "base_sha": "full reviewed base SHA",
  "base_ref": "develop",
  "head_ref": "feature/example",
  "head_repo": "OWNER/REPO",
  "findings": [],
  "standards_review": "clear",
  "spec_review": "clear",
  "required_contexts": ["actual-required-test-context"]
}
```

`required_contexts` is a nonempty list of real status context names for the reviewed head. Obtain requirements from the trusted base checkout and Gitea branch protections. Do not invent a success context, omit a failing requirement or count skipped/unrun tests as success. For repositories with local validation rather than CI, execute the required trusted-base commands, retain their full results, and publish a `codex/review-validation` commit status only after those actual commands succeed; list that context in the receipt. No validation mechanism means needs-human, not merge-ready.

Gitea routes used by the controller (all relative to `/api/v1`):

- GET `/repos/{owner}/{repo}/pulls?state=open&limit=50&page=N`
- GET `/repos/{owner}/{repo}/pulls/{number}` and its `/reviews`
- GET `/repos/{owner}/{repo}/issues/{number}/comments` and `/labels`
- GET `/repos/{owner}/{repo}/labels` to resolve exact label IDs
- POST `/repos/{owner}/{repo}/issues/{number}/labels` with `{"labels":[ID]}`
- DELETE `/repos/{owner}/{repo}/issues/{number}/labels/{id}` for only the obsolete review labels
- POST `/repos/{owner}/{repo}/issues/{number}/comments` for the review/repair report
- GET `/repos/{owner}/{repo}/commits/{sha}/statuses` for paginated statuses
- POST `/repos/{owner}/{repo}/statuses/{sha}` for actual local validation status (`state`, `context`, `description`, optional evidence `target_url`)

Use `Api` from `scripts/gitea_merge.py` for authenticated calls if no suitable Gitea adapter is available; it does not log the token and refuses redirects. Do not route these through `gh`. Server API schema: `https://gitea.example.test/swagger.v1.json` (inspect the deployed version before changing API assumptions).
