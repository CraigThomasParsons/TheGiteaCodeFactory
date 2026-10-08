# Outside-in tests for the kit's helpers

These tests check what each helper script does, seen only from outside:
command-line arguments, input files, environment variables and standard input
go in; standard output, standard error, the exit code and written files come
out. No test imports a helper's code. That is what lets the same tests judge
the original Python and JavaScript and the files generated from Haxe source
(see [decision record 0001](../../docs/adr/0001-haxe-as-the-source-language.md)):
a port is accepted only when this suite passes against both.

| Test file | Helper |
|---|---|
| `test_classify_execution.py` | `skills/supervise-agent-pipeline/scripts/classify_execution.py` |
| `test_parity.py` | `scripts/parity.py` |
| `test_install_skills.py` | `scripts/install-skills.py` |
| `test_coach.py` | `scripts/coach.py` |
| `test_dispatcher_gitea.py` | `skills/dispatcher/scripts/gitea.py` |
| `test_pipeline.py` | `skills/slice-pipeline/scripts/pipeline.py` |
| `test_reviewer.py` | `scripts/reviewer/ai_pr_reviewer.js` |
| `test_gitea_merge.py` | `skills/pr-review-resolve-loop/scripts/gitea_merge.py` |

## Running

```bash
python3 -m unittest discover -s tests/blackbox -p 'test_*.py' -v
```

`scripts/check-ci.sh` runs this. It needs Python 3.11 or later, Node 22 or
later and Git, and nothing else: no network, no Docker, no Haxe, no accounts.
It takes about half a minute.

Each test runs the helper with a clean environment and a temporary `HOME`, so
tokens, API keys or Gitea settings in your own shell never leak in. Helpers
that call Gitea or a model provider talk to a fake HTTP server on `127.0.0.1`
started by the test. `pipeline.py` gets fake `codex` and `tmux` programs on
`PATH` that record what they were asked and reply as scripted, so no agent or
tmux session is ever started.

## Pointing the suite at another implementation

By default each helper is run from its usual place in this checkout.

- `GCF_TOOL_ROOT=/path/to/tree` runs every helper from a directory laid out
  like this repository, for example an unpacked older commit:

  ```bash
  mkdir /tmp/base && git archive develop | tar -x -C /tmp/base
  GCF_TOOL_ROOT=/tmp/base python3 -m unittest discover -s tests/blackbox -p 'test_*.py'
  ```

- `GCF_TOOL_<NAME>=/path/to/file` replaces one helper, where `<NAME>` is the
  upper-case key in `TOOLS` in `support.py` (`CLASSIFY`, `COACH`,
  `DISPATCHER_GITEA`, `GITEA_MERGE`, `INSTALL_SKILLS`, `PARITY`, `PIPELINE`,
  `REVIEWER`).

A `.py` file runs with the Python running the tests and a `.js` file with
`node`.

## What the tests compare

- JSON output is parsed and compared as data, so key order and spacing do not
  matter. Fixed messages that people or scripts read (the parity `PASS` line,
  the skill installer's summary, documented error messages) are compared
  exactly.
- Exit codes are compared exactly where a helper documents them; argument
  errors handled by the command-line parser are only required to be non-zero.
- Times that depend on the clock are compared with a tolerance.
- Secret-shaped strings in `test_reviewer.py` are assembled at run time so the
  file does not trip the reviewer's own secret scan or other scanners.

## Current behavior worth knowing

The suite records today's behavior, including a few points a port must keep
unless a change deliberately alters them:

- `pipeline.py run` exits 0 even when a tick fails; the outcome is
  `"status": "blocked"` in `supervisor-status.json`.
- `gitea_merge.py` reports every refusal on standard output as
  `{"status": "blocked", ...}` with exit 1, and only successful results are
  appended to `merges.jsonl`.
- `gitea_merge.py --execute` sends the merge request once. If Gitea answers
  with an error, it reads the PR once more and reports `merged` only if the
  merge actually happened; it never retries.
- The reviewer posts `APPROVED` (Gitea's word) for a model's `APPROVE`, and a
  diff with secret-like content gets `REQUEST_CHANGES` without any provider
  being called.
- `classify_execution.py` treats any truthy value as a set flag, and a missing
  `processAlive` as alive.

Paths the tests cannot reach without real waiting (the pipeline's 20-minute
supervisor timeout, the reviewer's longer retry delays) and the reviewer's
Gemini call (its endpoint is fixed) are not covered here; the existing unit
tests still cover them until each helper is ported.
