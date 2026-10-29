# Haxe Style Guide

How Haxe code in this kit is written and reviewed. It applies to the helper
sources under `haxe/src/` and their tests under `haxe/test/`, and it is the
standard for the planned move of the kit's remaining Python and JavaScript
helpers to [Haxe](../glossary.md) (see the
[decision record](../adr/0001-haxe-as-the-source-language.md) and
[haxe-setup.md](../haxe-setup.md) for the toolchain).

Unlike the other files in this folder, this guide is written for this
repository, not copied from another project. It distils the shared rules of the
example guides here, mainly
[typescript_quality_architecture.md](typescript_quality_architecture.md) and
[unicode_and_hygiene_standards.md](unicode_and_hygiene_standards.md), plus the
common philosophy of [golang_style.md](golang_style.md),
[python_style.md](python_style.md),
[javascript_node_style.md](javascript_node_style.md) and
[ts_node_style.md](ts_node_style.md).

---

## 1. Principles

1. **Readable before clever.** Code is read far more often than written, and
   agents review it against this guide. Prefer the version a newcomer
   understands on first read.
2. **Explicit over compact.** Spell out types at boundaries, name intermediate
   values, and avoid chains that hide control flow.
3. **The compiler is the first reviewer.** The reason to use Haxe is strict
   static typing. Do not switch it off to make code compile.
4. **One behaviour, two targets.** Every helper may be compiled to Python 3 and
   JavaScript. Code must behave the same on both, and tests prove it.
5. **Comments explain intent.** Say *why* something is done, not what the next
   line does.

## 2. Naming

| Kind | Style | Example |
|---|---|---|
| Package | lower case, dot separated, rooted at `gcf` | `gcf.retalkbridge` |
| Type (class, interface, enum, abstract, typedef) | `UpperCamelCase` | `ReviewPolicy` |
| Function, variable, field | `lowerCamelCase` | `parseRepositoryName` |
| Constant (`static inline final`) | `UPPER_SNAKE_CASE` | `MAX_REVIEW_ROUNDS` |
| Enum constructor | `UpperCamelCase` | `Parked(reason)` |
| File | same as its main type | `ReviewPolicy.hx` |

- Use full, descriptive words: `repository`, `pullRequest`, `router`, not
  `repo`, `pr`, `rt`. Accepted short forms are those in [glossary.md](../glossary.md)
  and universal ones such as `id`, `url`, `sha`.
- Booleans read as questions: `isMerged`, `hasLabel`, `shouldRetry`.
- Functions are verbs (`loadConfig`), values are nouns (`config`).
- Single-letter names are allowed only for short loop indices.

## 3. Types

- **No `Dynamic` and no `untyped`** in kit code. Where a target API forces
  them (for example parsing JSON), contain them in one small boundary function
  that converts the value to a typed structure and validates it, and add a
  comment saying why.
- **Declare types on every public function**: parameters and return type.
  Local `var`/`final` may rely on inference when the type is obvious from the
  right-hand side.
- **Prefer `final` over `var`.** Use `var` only when the value really changes.
- **Null safety.** Compile with `--macro nullSafety("gcf", StrictThreaded)`
  (or `Strict` where threading is irrelevant). A value that can be absent is
  typed `Null<T>` and checked before use; everything else is non-null.
- **Model states with enums, not strings or flags.** An `enum` with
  constructor arguments makes impossible states unrepresentable and lets the
  compiler check every `switch` is exhaustive.
- **Use `abstract` types for distinct values that share a representation**,
  for example `abstract IssueNumber(Int)` versus `abstract PullRequestNumber(Int)`,
  so they cannot be swapped by mistake.
- **Use `typedef` structures for plain data** read from files or APIs, and
  `class` when there is behaviour or invariants to protect.
- Avoid `Any`, implicit casts and `cast` without a type. Use `Std.downcast`
  or pattern matching, and handle the failure case.

## 4. Structure

- One public type per file. Keep files short; split a file when it grows past
  roughly 300 lines or mixes concerns.
- Keep functions small and single-purpose. If a function needs a comment to
  separate its "steps", those steps are probably functions.
- Separate pure logic from input and output. Policy and parsing code takes
  values and returns values; a thin `Main` reads arguments, environment and
  files, calls the logic, and writes results. Pure code is what the tests
  cover most.
- **Target-specific code stays at the edge.** Put `#if python` / `#if js`
  blocks in small adapter modules, never inside business logic.
- Prefer early returns to deep nesting. Avoid nested ternaries; write
  `if`/`else` or a `switch` instead.
- No global mutable state. Pass dependencies in.

## 5. Errors and exit codes

- Represent expected failures as values: return an enum such as
  `Result<T>` with `Ok(value)` / `Failed(reason)` and make callers handle both.
- Throw only for programming errors and truly unexpected conditions; catch
  them in `Main`, print a clear message to standard error, and exit non-zero.
- Keep the exit-code contract of the helper being ported (for example exit
  75 for provider exhaustion where documented in [lifecycle.md](../lifecycle.md)).
- Error messages say what failed, with what input, and what to do next. Never
  include tokens or other secrets.

## 6. Comments and documentation

- Every public type and function has a doc comment (`/** ... */`) that states
  its purpose, parameters, return value and failure behaviour.
- Inline comments explain intent, constraints and non-obvious decisions.
  Delete comments that restate the code.
- Reference issues as `Refs #<n>` in commit messages, not in code, unless the
  code is a deliberate workaround that should be removed when the issue closes.
- Remove dead code instead of commenting it out.

## 7. Formatting and hygiene

- Indent with tabs as formatted by [haxe-formatter](https://github.com/HaxeCheckstyle/haxe-formatter)
  with a committed `hxformat.json`; do not hand-tune formatting.
- One import per line, sorted, no unused imports. No wildcard imports
  outside tests.
- **Source code is ASCII.** Following
  [unicode_and_hygiene_standards.md](unicode_and_hygiene_standards.md),
  ambiguous characters such as em dashes, smart quotes and non-breaking spaces
  are not allowed in `.hx` files. Markdown prose may keep them.
- Files end with a single newline and have no trailing whitespace.

## 8. Tests

- Test with utest under `haxe/test/`, mirroring the package of the code under
  test (`gcf.proof.Proof` is tested by `gcf/proof/ProofTest.hx`).
- Test behaviour that callers can observe, not private details.
- Run the suite on **both** targets; a test that passes on one target only is
  a failure.
- When porting a Python or JavaScript helper, first capture its current
  behaviour as tests (or fixtures of input and expected output), then port
  until those pass unchanged.
- Use isolated fixtures and mocked API responses, never live services.

## 9. Generated output

- Generated Python and JavaScript are committed with the
  `GENERATED FILE - DO NOT EDIT` header (see the drift check in
  [glossary.md](../glossary.md)). Change the Haxe source and rebuild; never edit
  the generated file by hand.
- Commit the source change and the regenerated output together.

## 10. Checks and rollout

Following the staged approach of
[typescript_quality_architecture.md](typescript_quality_architecture.md), each
check has one owner and new checks start as report-only before they gate.

| Concern | Tool | Status |
|---|---|---|
| Type correctness and build | `haxe` via `scripts/check-haxe.sh` | Gating (drift check in CI) |
| Unit tests on both targets | utest | Gating |
| Null safety | `nullSafety` macro | Report-only, then gating per package once clean |
| Format | haxe-formatter | Report-only, then gating |
| Lint | [haxe-checkstyle](https://github.com/HaxeCheckstyle/haxe-checkstyle) | Report-only, then gating |
| Ambiguous Unicode in `.hx` | Unicode audit | Advisory |

A port of an existing helper is complete when its behaviour tests pass on both
targets, the generated files are committed at the helper's existing path, and
the checks marked gating above pass.
