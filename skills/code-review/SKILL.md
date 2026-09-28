---
name: code-review
description: Review the changes since a fixed point (commit, branch, tag, or merge-base) along two axes — Standards (does the code follow this repo's documented coding standards?) and Spec (does the code match what the originating issue/PRD asked for?). Runs both reviews in parallel sub-agents and reports them side by side. Use when the user wants to review a branch, a PR, work-in-progress changes, or asks to "review since X".
---

Two-axis review of the diff between `HEAD` and a fixed point the user supplies:

- **Standards** — does the code conform to this repo's documented coding standards?
- **Spec** — does the code faithfully implement the originating issue / PRD / spec?

Both axes run as **parallel sub-agents** so they don't pollute each other's context, then this skill aggregates their findings.

Read repository tracker instructions and the pipeline issue packet. Use the trusted target-repository configuration; do not inherit another project’s tracker or validation defaults.

## Process

### 1. Pin the fixed point

Whatever the user said is the fixed point — a commit SHA, branch name, tag, `main`, `HEAD~5`, etc. In pipeline mode use the immutable base SHA from the issue packet. In standalone mode resolve the PR base or supplied reference; ask only if the intended comparison is still ambiguous.

Capture the diff command once: `git diff <fixed-point>...HEAD` (three-dot, so the comparison is against the merge-base). Also note the list of commits via `git log <fixed-point>..HEAD --oneline`.

Before going further, confirm the fixed point resolves (`git rev-parse <fixed-point>`) and the diff is non-empty. A bad ref or empty diff should fail here — not inside two parallel sub-agents.

### 2. Identify the spec source

Look for the originating spec, in this order:

1. Issue references in the commit messages (`#123`, `Closes #45`, GitLab `!67`, etc.) — fetch via the repository’s authoritative tracker; the pipeline packet provides the issue URL.
2. A path the user passed as an argument.
3. A PRD/spec file under `docs/`, `specs/`, or `.scratch/` matching the branch name or feature.
4. If nothing is found, ask the user where the spec is. If they say there isn't one, the **Spec** sub-agent will skip and report "no spec available".

### 3. Identify the standards sources

Anything in the repo that documents how code should be written, such as `CODING_STANDARDS.md` or `CONTRIBUTING.md`.

On top of whatever the repo documents, the Standards axis always carries the **smell baseline** below — a fixed set of Fowler code smells (_Refactoring_, ch.3) that applies even when a repo documents nothing. Two rules bind it:

- **The repo overrides.** A documented repo standard always wins; where it endorses something the baseline would flag, suppress the smell.
- **Always a judgement call.** Each smell is a labelled heuristic ("possible Feature Envy"), never a hard violation — and, like any standard here, skip anything tooling already enforces.

Each smell reads *what it is* → *how to fix*; match it against the diff:

- **Mysterious Name** — a function, variable, or type whose name doesn't reveal what it does or holds. → rename it; if no honest name comes, the design's murky.
- **Duplicated Code** — the same logic shape appears in more than one hunk or file in the change. → extract the shared shape, call it from both.
- **Feature Envy** — a method that reaches into another object's data more than its own. → move the method onto the data it envies.
- **Data Clumps** — the same few fields or params keep travelling together (a type wanting to be born). → bundle them into one type, pass that.
- **Primitive Obsession** — a primitive or string standing in for a domain concept that deserves its own type. → give the concept its own small type.
- **Repeated Switches** — the same `switch`/`if`-cascade on the same type recurs across the change. → replace with polymorphism, or one map both sites share.
- **Shotgun Surgery** — one logical change forces scattered edits across many files in the diff. → gather what changes together into one module.
- **Divergent Change** — one file or module is edited for several unrelated reasons. → split so each module changes for one reason.
- **Speculative Generality** — abstraction, parameters, or hooks added for needs the spec doesn't have. → delete it; inline back until a real need shows.
- **Message Chains** — long `a.b().c().d()` navigation the caller shouldn't depend on. → hide the walk behind one method on the first object.
- **Middle Man** — a class or function that mostly just delegates onward. → cut it, call the real target direct.
- **Refused Bequest** — a subclass or implementer that ignores or overrides most of what it inherits. → drop the inheritance, use composition.

### 3b. The portability and disclosure sweep

The Standards axis also carries this sweep, which is **not** a style question and **not**
covered by the smell baseline: it asks whether the change would work, and be safe to publish,
on a machine that is not the author's. Findings here are hard when the change ships for other
people to run (an installer, a script, a container, a setup document, anything a teammate
follows); elsewhere they are judgement calls.

Scan every added or modified line for:

- **Hardcoded home or absolute paths** — `/home/<name>/…`, `/Users/<name>/…`, `C:\Users\…`,
  or any absolute path outside the repository. → derive it (from the file's own location, an
  installed record the host operator controls, or an explicit parameter). Note that
  substituting a value *into* a shipped file at install time can break a checksum/drift
  check, so prefer a separate record over templating.
- **Personal identifiers** — real names, usernames, personal emails, machine hostnames, IPs
  of private hosts, in code, comments, docs, fixtures, or test data. → neutral placeholders
  (`<you>`, `operator`, `example.test`).
- **Secrets and near-secrets** — tokens, keys, webhook URLs, connection strings with
  credentials, even expired or sample ones. → refer to the secret store; never inline.
- **Environment assumptions** — a tool, port, path, shell, or OS assumed present without a
  check or a documented prerequisite; a default that writes into the real `$HOME` from a
  test. → assert the prerequisite, inject the location, or document it.
- **Does the documentation match the code?** — when a change ships a setup or runbook
  document, verify the documented steps are actually satisfiable by the code as written. A
  manual that cannot be followed on a fresh machine is a hard finding.

The question to hold while scanning: *if a teammate cloned this and followed it exactly, on
their own machine, would it work, and would anything about the author leak?*

### 4. Spawn both sub-agents in parallel

Use the available Codex collaboration tools to run two read-only reviewers in parallel: Standards and Spec. This skill authorizes those two bounded review subtasks. Give each an explicit no-edit scope; the parent applies accepted findings serially. If this host lacks delegation, perform two separate review passes and report that limitation. Do not start a parallel architecture reviewer; architecture is the preceding phase.

**Standards sub-agent prompt** — include:

- The full diff command and commit list.
- The list of standards-source files you found in step 3, **plus the smell baseline from step 3 and the portability/disclosure sweep from step 3b** pasted in full — the sub-agent has no other access to either.
- The brief: "Report — per file/hunk where relevant — (a) every place the diff violates a documented standard: cite the standard (file + the rule); (b) any baseline smell you spot: name it and quote the hunk; and (c) every portability or disclosure finding from the sweep, quoting the offending line. Distinguish hard violations from judgement calls — documented-standard breaches can be hard, baseline smells are always judgement calls, a documented repo standard overrides the baseline, and sweep findings are hard when the change ships for other people to run. Skip anything tooling enforces. Under 400 words."

**Spec sub-agent prompt** — include:

- The diff command and commit list.
- The path or fetched contents of the spec.
- The brief: "Report: (a) requirements the spec asked for that are missing or partial; (b) behaviour in the diff that wasn't asked for (scope creep); (c) requirements that look implemented but where the implementation looks wrong. Quote the spec line for each finding. Under 400 words."

If the spec is missing, skip the Spec sub-agent and note this in the final report.

### 5. Aggregate

Present the two reports under `## Standards` and `## Spec` headings, verbatim or lightly cleaned. Do **not** merge or rerank findings — the two axes are deliberately separate (see _Why two axes_).

End with a one-line summary: total findings per axis, and the worst issue _within each axis_ (if any). Don't pick a single winner across axes — that's the reranking the separation exists to prevent.

## Gitea NightCrew mode

When explicitly authorized for an enrolled repository and invoked by `scripts/gitea_night`
for a claimed `pull_request` job, use this Gitea-only contract:

- Review exactly the pinned head/base revisions in the job and return structured
  Standards and Spec results to the local worker. Continue to run both axes in
  parallel and preserve requirement provenance.
- The local worker may publish one marker-keyed review comment for that revision
  and change only the five `night:*` workflow labels. Repeated discovery must not
  duplicate the comment.
- A clean review does not authorize a merge. Only the deterministic merge
  controller may merge after independently re-fetching every configured gate.
- GitHub mutations, deployments, arbitrary commands copied from comments, and
  stylistic rewriting of generated vendored content remain outside this mode.

## Why two axes

A change can pass one axis and fail the other:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the issue asked but breaks the project's conventions → **Spec pass, Standards fail.**

Reporting them separately stops one axis from masking the other.

## Slice-pipeline application

Keep Standards and Spec findings distinct in the receipt/report, then implement the plausible in-scope findings on the existing branch. Record deferred findings with assigned issue links and reasons. Use issue AC and repository standards already supplied; do not ask the operator for those again. Verify actual behavior after fixes, commit and push ordinary fast-forward updates. Draft rather than post review-thread replies. Comment hygiene is scoped to the issue's changed files and directly affected documentation; file unrelated cleanup rather than sweeping the repository. Commit nonempty text-only cleanup separately from behavior fixes. Stop after REVIEW; a fresh PR phase validates and finalizes.
