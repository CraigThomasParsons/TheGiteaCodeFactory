# 1. Haxe is the source language for the kit's helper scripts

Date: 2026-10-08

Status: Accepted

## Context

The kit's executable helpers are written in two languages. Seven are Python 3
scripts (about 600 lines, standard library only) and one is a Node.js script
(the advisory reviewer, about 900 lines of plain JavaScript with no npm
packages). There is no TypeScript. Moonlighter, the optional coordinator in
[moonlighter/](../../moonlighter/), adds about 1,850 lines of Python: its worker
client (`scripts/gitea_night/`) and its Paperclip bridge
(`scripts/tools/paperclip_bridge.py`).

| Helper | Path today | Called by |
|---|---|---|
| Merge gate | `skills/pr-review-resolve-loop/scripts/gitea_merge.py` | agents, per the skill |
| Dispatcher Gitea adapter | `skills/dispatcher/scripts/gitea.py` | agents, per the skill |
| Slice pipeline driver | `skills/slice-pipeline/scripts/pipeline.py` | agents, per the slice and tmux pipeline skills |
| Execution classifier | `skills/supervise-agent-pipeline/scripts/classify_execution.py` | agents, per the skill |
| Coach | `scripts/coach.py` | agents, per the coach skill |
| Parity comparator | `scripts/parity.py` | agents, per the parity skill |
| Skill installer | `scripts/install-skills.py` | operators, per the README and onboarding guide |
| Advisory reviewer | `scripts/reviewer/ai_pr_reviewer.js` | the `pr-ai-review.yml` workflow in an enrolled repository |

The author wants one source language for all of them:
[Haxe](https://haxe.org/), a statically typed language whose compiler
generates code for several targets, including Python 3 and JavaScript. One
language means one type system, one test framework and one set of review
habits, while each helper still runs where it runs today.

Three facts limit the options:

1. **Callers use fixed paths and interpreters.** Skills tell agents to run, for
   example, `python3 scripts/gitea_merge.py`. The reviewer workflow fetches the
   factory at a pinned commit and runs `node scripts/reviewer/ai_pr_reviewer.js`.
2. **Helpers are copied into other repositories.** `install-skills.py` copies
   whole skill directories, scripts included, into a project that has no Haxe.
3. **The Actions runner image has no Haxe.** The `factory-node` label maps to
   `node:22-bookworm`, which provides Node 22, Python 3.11, Git and Bash
   ([setup.md](../setup.md)).

## Decision

**1. Targets.** Haxe source compiles to **Python 3** for the seven Python
helpers and to **JavaScript for Node.js** (using the
[hxnodejs](https://lib.haxe.org/p/hxnodejs/) bindings) for the advisory
reviewer. Native targets (HashLink, C++) and running Haxe's interpreter at
call time (`haxe --run`) are not used.

**2. Generated files are committed at today's paths.** Each helper's generated
output replaces the hand-written file at the same path, with the same name and
interpreter, so no skill, workflow or document needs a new command. Every
generated file starts with a header saying it is generated, naming its Haxe
source and build file, and telling readers not to edit it. Agents and people
who want to read or change a helper go to its Haxe source.

**3. Folder layout.**

```text
.haxerc                     # pinned Haxe version, in lix format
haxe_libraries/             # pinned library versions (utest, hxnodejs), in lix format
haxe/
  toolchain.env             # versions, download URLs and SHA-256 checksums
  src/gcf/<helper>/         # Haxe source, one package per helper
  test/                     # utest suites for the Haxe code
  build/<artifact>.hxml     # one build file per generated file
  generated/                # generated files that have no historical path (for example the toolchain proof)
tests/blackbox/             # language-neutral tests of each helper's command-line behavior
```

[lix](https://github.com/lix-pm/lix.client) is a Haxe version and library
manager. Its file formats are used for the pins so that lix users get the same
versions, but the kit's own scripts read those files themselves and do not
require lix.

**4. Toolchain pin and CI.** Haxe 4.3.7 (the current stable release), utest
and hxnodejs are pinned by version, and the downloads by SHA-256.
`scripts/install-haxe.sh --ci` downloads the pinned compiler and libraries into
a temporary directory on every CI run; no custom runner image is built.

**5. Drift check.** `scripts/check-haxe.sh` rebuilds every generated file into a
temporary directory and fails if any differs from the committed copy, then runs
the utest suites. It fails when Haxe is missing unless `CHECK_SKIP_HAXE=1` is
set, the same way `check-local.sh` treats a missing Docker CLI.
`scripts/check-ci.sh` calls it, so CI rejects a hand-edited generated file or a
Haxe change whose output was not rebuilt and committed.

**6. Test strategy: an outside-in parity suite plus utest.**

- Before any helper is ported, `tests/blackbox/` gains tests that drive each
  helper only through its command line: arguments, input files, environment and
  standard input go in; standard output, standard error, exit code and written
  files come out. Helpers that call Gitea or a model provider talk to a fake
  server on `localhost`. The suite can be pointed at any implementation, so the
  same tests run against the current Python or JavaScript (the oracle) and the
  Haxe output (the port).
- The existing unit tests (`tests/test_factory.py`, the merge-gate tests, the
  pipeline tests and the reviewer's `node:test` file) reach into module
  internals that generated code does not reproduce. They keep running against
  the old code until that helper's port lands, and are deleted with the old
  source in the same change.
- New unit tests for Haxe code use [utest](https://lib.haxe.org/p/utest/), run
  on Haxe's interpreter and on the generated target.

**7. Slice order.** One helper per change, smallest and least risky first:

1. this decision record;
2. toolchain: install, build and check scripts, pins, CI wiring and a setup
   guide (`docs/haxe-setup.md`), proven on a small program with no product
   behavior;
3. the outside-in suite for all eight helpers, against the current code;
4. `classify_execution.py` (pure logic) as the pilot port;
5. `parity.py` and `install-skills.py`;
6. `coach.py`;
7. the dispatcher's `gitea.py`;
8. `pipeline.py`;
9. the advisory reviewer, pure helpers first, then its network code;
10. `gitea_merge.py`, last (see 9 below);
11. cleanup: provenance, catalog and validation records.

A port changes only the helper it names. It is accepted when the outside-in
suite passes on both the base commit (old code) and the change (generated code),
and the generated file is byte-for-byte what the build produces.

**8. Moonlighter is in scope, ported in its upstream.** Moonlighter's Python
(`scripts/gitea_night/*`, `scripts/tools/paperclip_bridge.py` and their pytest
suites) will be converted too. Moonlighter's code is maintained in a separate
upstream repository and copied here by `scripts/sync-moonlighter.sh` (see
[moonlighter.md](../moonlighter.md)), so the ports are made there and brought
over by a normal sync; `moonlighter/` is not edited in this repository. Its
three small front-end JavaScript files (Vite and Laravel Echo boilerplate) are
out of scope. Before porting, the upstream needs its own outside-in suite:

- the worker, run as `python3 -m gitea_night.worker` (through
  `scripts/gitea-night-worker`), with a fake Gitea and a fake coordinator API
  on `localhost`, stub agent commands on `PATH`, a temporary `HOME` and
  `XDG_STATE_HOME`, and Git repositories created in a temporary directory;
- the bridge's subcommands (`tick`, `handoff`, `clear-halt` and the others in
  its runbook), with a temporary config file, a fake coordinator API and token
  environment variables;
- the same "point it at either implementation" switch as `tests/blackbox/`.

The sync script's leak checks must also accept the generated files and the
`haxe/` tree.

**9. The merge gate goes last, after the review loop is proven live.**
[Roadmap milestone 1](../roadmap.md#1-prove-the-review-loop-live) proves the
merge gate against a real Gitea: a reviewed PR merges, a stale head is refused
and a failing test blocks the merge. That evidence is tied to the exact code of
`gitea_merge.py`. The merge gate is therefore ported only after milestone 1 is
recorded in [validation.md](../validation.md), and its port must repeat the
stale-head and failing-test checks on the live demo repository before it is
accepted.

## Consequences

- Callers do not change: the same paths, interpreters and arguments keep
  working, including in repositories that received copied skills.
- Running a helper needs only Python 3 or Node.js, as today. Changing one needs
  Haxe 4.3.7 and the pinned libraries; the setup guide added with the toolchain
  (`docs/haxe-setup.md`) explains how to install them.
- Generated files are much larger than the hand-written ones, because each
  carries a copy of the Haxe runtime it uses (a ten-line program becomes about
  1,600 lines of Python). They are not meant to be read; the header points to
  the source.
- Every CI run downloads about 10 MB for the compiler and libraries. The
  checksums make that download reproducible; it depends on the runner having
  internet access.
- The Haxe Python output's standard library has no bindings for some modules
  the helpers use (`fcntl`, `urllib.request`, `http.client`, `argparse`), so
  ports add small binding (`extern`) classes for them.
- `docs/provenance.json` records most helpers as copies of files from
  elsewhere. After a port, the kit's Haxe source is the source of truth, and
  each record is updated to say the file is derived from that copy. The
  original copies are not changed.
- The JavaScript target emits CommonJS `require` calls, while this repository's
  `package.json` declares ES modules. The build adds a two-line prologue that
  defines `require` with Node's `createRequire`, so generated `.js` files run
  in either mode.

## Alternatives considered

- **HashLink or C++ native binaries.** Rejected: a binary per CPU architecture,
  binaries in Git, an extra runtime on every runner and worker, and no simple
  way to ship them inside copied skill folders.
- **Running Haxe at call time (`haxe --run` or the interpreter).** Rejected:
  every worker, every enrolled repository's CI and every agent would need Haxe,
  and every documented command would change.
- **Compiling everything, including the reviewer, to Python.** One target is
  simpler, but the reviewer workflow template runs `node`, and repositories
  that already copied it would break. Kept open as a later simplification.
- **Building generated files in CI instead of committing them.** Rejected:
  copied skills and the pinned-commit reviewer checkout would then contain no
  runnable file.
- **A custom runner image with Haxe preinstalled.** Not chosen for now: the
  per-run download is simpler to maintain, and needs no runner administration.
