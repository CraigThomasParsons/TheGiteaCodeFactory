# PR review, repair and auto-merge

## Choose an owner

Use either the standalone skills below or the NightCrew worker described in
[nightcrew.md](nightcrew.md). Their labels and receipt formats are different.
Do not run both controllers on the same PR.

The Gemini reviewer (below) is an optional **advisory** check. The
`night-shift-review-task:v1` marker it leaves on a PR is not a current-head merge
authorization.
The strict merge gate uses independent review plus actual validation evidence.

## Standalone skills

On the worker host, authenticate the agent and set `GITEA_SERVER_URL` and
`GITEA_TOKEN_FILE` as in [setup](setup.md). Invoke the installed skill in a trusted
project checkout with an explicit repository and bounded scope:

```text
Use $pr-review-resolve-loop for owner/project on the configured Gitea server.
Process at most two enrolled PRs, up to three repair rounds each.
Project auto-merge is enabled; merge only after the receipt and current checks pass.
```

For review only, invoke `$pr-review-loop`; for repair only, `$pr-resolve-loop`.
These are agent workflows, not names of shell executables. The documented command
for a deterministic merge check is:

```bash
python3 skills/pr-review-resolve-loop/scripts/gitea_merge.py \
  --repo owner/project --pr 123 --method squash \
  --receipt "$HOME/.local/state/gitea-pr-review-resolve/owner-project/123/receipt.json"
```

Without `--execute` this makes read-only eligibility checks. The authorized
controller adds `--execute` only after verifying project auto-merge policy.
The script does not load the project policy JSON or infer user authorization.

Flow: `review:requested` → independent review → `review:findings` → repair →
`review:resolved` → `review:requested` → current-head clear → merge.
Unresolved decisions use `review:needs-human`. Remove only obsolete state labels.

The helper requires matching repository, PR, base/head, source/target branch
identities, no unresolved findings, both review axes clear, current validation
contexts successful, an open/non-draft/mergeable PR and no conflicting labels.
It also blocks on any published pending/failing current-head status. It rechecks
before a non-force merge and verifies the resulting merged SHA. Server-side
protection remains essential for concurrent base or label changes.

Read the [receipt contract](../skills/pr-review-resolve-loop/references/receipt.md).
A timestamp or label alone is not proof. Local test results can be published as
`codex/review-validation` only after the trusted commands actually pass.

## Gemini advisory Actions reviewer

`scripts/reviewer/ai_pr_reviewer.js` tries a chain of model providers in order and
runs a heuristic secret-pattern scanner over the diff. It takes explicit project and
API inputs and fails closed if it cannot fetch the PR diff.

Copy `templates/pr-ai-review.yml` into the target's `.gitea/workflows/` and configure:

- Variables: `FACTORY_URL` (reachable HTTPS clone URL), `FACTORY_REVISION` (reviewed
  full commit SHA), `GEMINI_MODEL` (available model for your account).
- Secret: `GEMINI_API_KEY`; the workflow uses the Gitea job token for target reads
  and review writes. Verify that token's permissions in the canary.
- Project styles: defaults are `docs/style/javascript_node_style.md` and
  `docs/style/ts_node_style.md`; override the corresponding environment paths or
  adapt the prompt for another language. Missing style files produce empty guidance,
  so a generic run is not evidence that project-specific standards were reviewed.

Factory clone must be accessible without embedding credentials in its URL.
For a private factory repository, provision a separate read-only checkout credential
and reviewed credential-helper setup rather than reusing a write token in the URL.
Optional provider environment inputs are documented by the script: MAMMOUTH,
GROQ and OLLAMA keys/models/base URLs; they are opt-in and not enabled by this template.

The job executes factory code pinned by SHA and reads style guidance from the
trusted target branch; it never checks out and executes PR code. Workflows themselves
must remain trusted: restrict workflow-editing rights and fork secret exposure.
Only review data goes to configured model providers. The heuristic secret
scanner is an aid, not a guarantee that diffs contain no sensitive data.

The factory's root `package.json` supplies ESM mode. Keep the script inside that
checkout; copying it alone into a CommonJS project requires `.mjs` or equivalent
module configuration.
