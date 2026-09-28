# TypeScript Quality Architecture

> **Example guide.** Written for AgileMedievalPeasantBoard's TypeScript front end; issue numbers, phases and paths refer to that repository; included as a worked example. Copy it into your
> project and replace the project-specific parts. See [README.md](README.md).

How TypeScript code quality is checked in this repo, who owns which check,
and the staged rollout order for new tooling.

Written 2026-06-15 as the deliverable of issue #250 (Phase 12D — Developer
Tooling & Code Quality). This is the **foundation slice**: it audits, decides
tool roles, documents the architecture, and adds a canonical `quality:ts`
umbrella over the checks that already exist. It introduces **no new
dependency** and **no enforcement**. Later slices add real tools — see the
rollout order at the bottom.

This document is the frontend counterpart of `php_style.md` for what *checks*
the code (not what *the code looks like* — that's `ts_node_style.md` and
`frontend_architecture.md`).

---

## TL;DR

| Concern | Tool | Status | Issue |
|---|---|---|---|
| Type correctness | `tsc` (TypeScript compiler) | In place | — |
| TSDoc / JSDoc presence | `scripts/ts-docblocks/check.mjs` | In place (red — debt) | — |
| Unit tests | Vitest | In place | — |
| E2E behaviour | Cucumber + Playwright | In place | — |
| Strictness ratchet | `tsc` strict flags (`tsconfig.strict.json` / `tsc:strict`) | Report-only (non-gating) | #251 |
| Lint (correctness rules) | ESLint + typescript-eslint | Report-only (non-gating) | #252 |
| Format / import order | Biome | Report-only (non-gating) | #253 |
| Dead code / spelling | Knip / CSpell (`hygiene:ts`) | In place (advisory, non-gating) | #254 |
| Unicode normalization | `unicode_dash_audit.py` policy + tool | Policy + tool in place; bounded passes | #254/#255 |

The canonical umbrella script is `npm run quality:ts`. Today it runs `tsc:game`
only. Later slices grow it as new tools land and existing debt is paid.

---

## 1. Current state (audited 2026-06-15)

Confirmed against the live repo on branch
`feature/250-typescript-tooling-foundation`.

**Type checking**
- `npm run tsc:game` runs `tsc -p tsconfig.game.json`. Currently green.
- `npm run build` runs `tsc -p tsconfig.game.json && vite build`, so type
  errors break the production build.
- Watch mode: `npm run tsc:game:watch`.
- `npm run tsc:strict` runs `tsc -p tsconfig.strict.json` — the check-only
  strict lane added by #251. It is **report-only and non-gating**: it extends
  `tsconfig.game.json` with `strict: true` + `noEmit: true`, is NOT referenced
  by `build`/`tsc:game`, and is NOT part of `quality:ts`/`test:all`. It is
  expected to print errors (394 at introduction — see §8). Cleanup happens
  later, folder-by-folder.

**Docblock presence**
- `npm run docs:ts:check` runs `scripts/ts-docblocks/check.mjs`. It walks
  `resources/game/**` and reports missing JSDoc, missing `@param`, and
  missing `@returns` on top-level functions.
- Watch mode: `npm run docs:ts:watch`.
- **Currently red.** Audit on 2026-06-15 found 200 violations across 33
  files (20 engine modules + 13 test files). This is pre-existing debt, not
  caused by this slice. Backfill is a separate concern from architecture —
  see [Section 5](#5-known-debt) for the resolution path.

**Tests**
- `npm test` runs Vitest (`vitest run`). 260 tests in 22 files, green.
- `npm run test:e2e` runs Cucumber.js + Playwright over `tests/e2e/features`.

**TypeScript configs**
- `tsconfig.json` — editor / app config. Used by editor TS
  (`resources/js/editor/**`, the React map editor) and tests in
  `resources/game/test/**`. `module: ESNext`, `moduleResolution: bundler`,
  `strict: false`, `noEmit: true`.
- `tsconfig.game.json` — engine config. Used by `npm run tsc:game` and
  `npm run build`. `module: none` (script-tag globals), `noEmit: false`,
  `outDir: public/game/script`, `strict: false`.
- `tsconfig.strict.json` — check-only strict lane (#251). `extends`
  `tsconfig.game.json` with `strict: true` + `noEmit: true`. Used only by
  `npm run tsc:strict`. Never emits, never gates — see §8.

**Linting**
- `npm run lint:ts` runs `eslint resources/game resources/js` over the owned
  TypeScript surface using the flat config `eslint.config.mjs`. Type-aware
  rules are enabled via a lint-only program (`tsconfig.eslint.json`). Added by
  #252. It is **report-only and non-gating** — NOT referenced by `quality:ts`,
  `build`, or `test:all`, and expected to print findings. See §9 for the rule
  policy, the introduction baseline, and the cleanup targets.
- `npm run lint:ts:fix` runs the same with `--fix`, applying only the
  autofix-safe rules (`eqeqeq`, `no-implicit-coercion`).

**Formatting**
- Biome is installed (`@biomejs/biome`, dev dependency) and configured as a
  **formatter only** (linter disabled) via `biome.json`. Run report-only with
  `npm run format:ts:check`; apply with `npm run format:ts`. It is **non-gating**
  — deliberately NOT in `quality:ts`/`test:all` yet — see §10.

**Hygiene (added by #254, advisory)**
- `npm run hygiene:ts` runs Knip (`knip.json`) then CSpell (`cspell.json` +
  `.cspell/project-words.txt`). Non-gating: NOT in `quality:ts` or `test:all`.
- `npm run hygiene:unicode` runs `scripts/tools/unicode_dash_audit.py --check`.
- Full operating manual: `docs/style/unicode_and_hygiene_standards.md`.

---

## 2. Tool roles (ownership boundaries)

Each check owns exactly one concern. Overlap creates noise, fights between
tools, and unclear failure messages. The boundaries below are the contract.

### 2.1 `tsc` — type correctness only
Owns: types, signatures, missing properties, unsafe casts (once strict is on).
Does not own: stylistic rules, formatting, import order, unused-variable
warnings (those are the linter's job).

There are **two** tsc configs by design:

- **Engine TS** (`tsconfig.game.json`): `module: none` because the engine
  loads as script tags into `window.RTS.*` globals (see
  `frontend_architecture.md` §1). This is the config the production build
  uses.
- **Editor / test TS** (`tsconfig.json`): `module: ESNext` because the React
  map editor and Vitest tests use a real module system.

Both share `target: ES2020`, `strict: false`, and `lib: ["ES2020", "DOM"]`.
The strictness ratchet (#251) lifts `strict` toward `true`, in order:
`noImplicitAny` → `strictNullChecks` → full `strict`. Engine TS goes first
because it has the smaller surface and is the production hot path. The first
step is a check-only report lane (`tsconfig.strict.json` / `npm run
tsc:strict`) that leaves the emit configs at `strict: false`; see §8 for the
baseline, flag order, and folder-by-folder cleanup workflow.

### 2.2 `scripts/ts-docblocks/check.mjs` — JSDoc presence
Owns: presence of a JSDoc block on every top-level function in
`resources/game/**`, including `@param name` for every parameter and a
`@returns` tag. Mirrors the PHP-side `docs:php:check` convention.

Does not own: docblock content quality, prose style, or `@throws`
correctness. It is presence-only — humans review the words.

### 2.3 ESLint + typescript-eslint — correctness rules (#252, report-only)
Owns: lint rules that prevent real bugs and enforce explicit-intent style
that this project already requires by convention but does not currently
enforce. Landed in #252 as a non-gating report (see §9). The first-pass rule
set, split by how it is enforced:

**Type-aware bug catchers (`error`; review-required, no safe autofix):**
- `@typescript-eslint/no-floating-promises`.
- `@typescript-eslint/no-misused-promises`.
- `@typescript-eslint/switch-exhaustiveness-check`.

**Project-convention rules (`warn` during rollout; review-required):**
- `no-ternary` (project rule — `?:` is banned in TS/JS, see memory feedback).
- `no-console` (CLAUDE.md: no committed `console.log`).
- `@typescript-eslint/no-explicit-any`.

**Autofix-safe (`error`; applied by `lint:ts:fix --fix`):**
- `eqeqeq` (no `==`/`!=`).
- `no-implicit-coercion`.

**Deliberately deferred:**
- `@typescript-eslint/no-unnecessary-condition` — only reports correctly once
  `strictNullChecks` is on (the #251 ratchet has not yet landed that in the
  emit config). Enable it alongside that flag.

Does not own: formatting (whitespace, semicolons, quote style, import
ordering) — that's the formatter's job. ESLint is configured to **defer** any
formatting rule and let the formatter handle it; this prevents ESLint↔Biome
fights.

### 2.4 Biome — formatting + import order (landed, #253)
Owns: indentation, whitespace, semicolons, quotes, trailing commas, import
sort order, line-length wrapping. One canonical output the whole repo agrees
on.

Does not own: any correctness rule. Biome is configured with `linter.enabled:
false` so it never disagrees with ESLint (#252) — the formatter formats, the
linter lints, and the two surfaces do not overlap.

Import order is part of Biome's job, but `biome format` only touches
whitespace. Import sorting is a Biome *assist* action, so the scripts run
`biome check` (formatter + assist, linter off), not `biome format`. The engine
surface (`module: none`) has no imports, so import sorting only affects the
editor/test files that use real `import` statements.

Why Biome and not Prettier: speed (Rust, single binary, no plugin sprawl)
and built-in import sorting. The trade-off is a smaller plugin ecosystem,
which is fine for a project that wants formatting opinions to be fixed.

Config (`biome.json`, tuned to the existing house style so adoption is a
no-op for already-conforming code): 4-space indent, single quotes, semicolons
always, trailing commas, 100-column line width, LF endings. Scoped to
`resources/game/**` and `resources/js/**`; `public/**` (the compiled engine
JS), `vendor/**`, `node_modules/**`, and `storage/**` are excluded. See §10 for
the baseline drift and the bounded rollout rules.

### 2.5 Knip + CSpell — hygiene (in place, advisory, #254)
- **Knip** (`knip.json`) owns: dead code, unused exports, unused dependencies,
  unused files — for the **module-based** TS only (the React editor in
  `resources/js` + node tooling). The `module: none` engine
  (`resources/game/script/**`) has no import graph for Knip to follow and is
  deliberately out of scope until the ESM/pixi migration. Advisory (warn-only),
  promoted to a gate only once the backlog clears.
- **CSpell** (`cspell.json` + `.cspell/project-words.txt`) owns: spelling in
  source code and comments. Language is `en,en-GB` (this repo writes British
  English). Game/stack terms live in the dictionary, not in `// cspell:ignore`
  pragmas. Vendored/minified/compiled-output and foreign-text reference dirs
  are excluded.

Both run via `npm run hygiene:ts`. Does not own anything the compiler, linter,
or formatter already owns. Full detail: `unicode_and_hygiene_standards.md`.

### 2.6 Unicode normalization (policy + tool in place, #254; bounded passes #255)
Owns: normalizing the two ambiguous dash codepoints that actually occur in this
repo — `U+2014` EM DASH and `U+2013` EN DASH — to ASCII `-` in **code** files,
while keeping em dashes in Markdown prose (the allowed exception). The tool is
`scripts/tools/unicode_dash_audit.py` (bounded `--check`/`--fix`, hard
exclusions for vendored/minified/compiled output), not a new dependency. The
policy, the safe-vs-review-required classes, and the bounded Night Shift pass
workflow live in `unicode_and_hygiene_standards.md`. The mass `--fix` rollout is
run folder-by-folder as bounded passes (#255 / Night Shift), not in #254.

---

## 3. Canonical npm-script surface

The umbrella name is `quality:ts` to match the existing `test:*` / `docs:*`
naming style and to signal "static quality of TS, no test runs".

### Today (this slice)
```jsonc
"quality:ts": "npm run tsc:game"
```

That is the only check that is currently both implemented and green over the
whole codebase. Running it tells you "the types compile".

### Final shape (after #251–#254)
```jsonc
"quality:ts":         "npm run tsc:game && npm run lint:ts && npm run format:ts:check && npm run docs:ts:check"
"lint:ts":            "eslint resources/game resources/js --max-warnings=0"
"lint:ts:fix":        "eslint resources/game resources/js --fix"
"format:ts":          "biome check --write resources/game resources/js"
"format:ts:check":    "biome check resources/game resources/js"
"hygiene:ts":         "knip ; cspell \"resources/**/*.{ts,tsx,mjs}\" --no-progress"   // advisory (#254)
"hygiene:unicode":    "/usr/bin/python3 scripts/tools/unicode_dash_audit.py --check"  // advisory (#254)
```

Order matters: type errors first (they cascade), then lint (semantics), then
format (cosmetic), then docblocks (presence). Each fails fast.

`hygiene:ts` is intentionally **not** part of `quality:ts` — it advisory,
not gating, and runs as its own job so it does not block PRs while debt is
paid down. It is promoted into `quality:ts` only when the dead-code backlog
is clear.

### Local vs CI

- **Local fast loop**: `npm run tsc:game:watch` + `npm run test:watch` while
  editing. `npm run quality:ts` before pushing.
- **CI / `test:all`**: `npm run test:all` already runs the chain (php → tsc
  → vitest → build → cucumber). The strictness, lint, and format checks
  will fold into this chain as their issues land — slot order is "after
  `tsc:game`, before `test`".
- **Night Shift**: the autonomous agent runs `quality:ts` after each phase
  and before opening a PR. New tools must be safe to run in a non-TTY
  environment (Biome and ESLint both are).

---

## 4. Game TS vs editor TS

The two TS surfaces are different enough that some checks treat them
differently. Document why up front so future slices don't trip on it.

| Aspect | Engine TS (`resources/game/script/**`) | Editor TS (`resources/js/editor/**`) |
|---|---|---|
| tsconfig | `tsconfig.game.json` | `tsconfig.json` |
| Module system | `module: none` (script tags, `window.RTS.*` globals) | `module: ESNext`, real imports |
| Build | `tsc` emits to `public/game/script/` | Vite bundles |
| Architecture target | ECS, eventually (`frontend_architecture.md` §3) | React + react-dom |
| Lint config (future #252) | engine-focused rules, `no-console: error` | React-aware rules, react-hooks plugin |
| Format (future #253) | Same Biome config | Same Biome config |
| Docblocks | Required (already enforced via `docs:ts:check`) | Required (same script, same rule) |
| Tests | Vitest in `resources/game/test/**` | Vitest + Playwright (editor smoke in e2e) |

**Single source of truth for "where do these checks run":** the umbrella
scripts above point at both surfaces; per-tool configs encode the per-surface
specifics.

---

## 5. Known debt

Captured during the Phase 1 audit on 2026-06-15. These are pre-existing
conditions, not caused by this slice.

### 5.1 `docs:ts:check` is currently red (200 violations)
- **Engine modules** (~20 files): `ai.ts`, `building.ts`, `buildingAnimate.ts`,
  `cursor.ts`, `fog.ts`, `gameLoop.ts`, `gameMenu.ts`, `harvest.ts`,
  `hud.ts`, `orcAiSync.ts`, `outcomeScreen.ts`, `production.ts`, `road.ts`,
  `script.ts`, `sprite.ts`, `tabLease.ts`, `techTree.ts`, `topBarMenu.ts`,
  `trees.ts`, `unitTypes.ts`.
- **Test files** (~13 files): mostly missing `@returns` on `bootXxx`
  helpers.

**Why `docs:ts:check` is NOT in `quality:ts` today**: adding it now would
flip the umbrella red on introduction, which would either (a) get ignored
in CI and lose its value, or (b) be wired around with `--no-verify` style
escapes. Neither is acceptable.

**Resolution path**: a backfill issue (analogous to the PHP-side #152
docblock standards work) should clear the 200 violations, then a one-line
follow-up PR adds `&& npm run docs:ts:check` to `quality:ts`. The check is
**already runnable** — `npm run docs:ts:check` works today — it's just not
yet part of the gating umbrella.

### 5.2 Strictness, lint, and formatting reported but not enforced
As of #251, strict type errors are **measured** (`npm run tsc:strict` — 394
errors, see §8) but not yet enforced; the emit build stays `strict: false`
until cleanup retires the gap. As of #252, lint findings are likewise
**measured** (`npm run lint:ts` — 368 findings, see §9) but not enforced. As of
#253, formatting drift is **measured** (`npm run format:ts:check` — 69 of 76
files, see §10) but not yet applied; the code is not mass-reformatted and
`format:ts:check` is not in `quality:ts`. The fact that today's `quality:ts` is
a one-line umbrella is the point: there is nowhere to hide the absence of these
gates.

### 5.3 Hygiene advisory baselines (added by #254)
Advisory only — none of this gates a PR; each is a candidate backlog.
- **Knip:** unused devDeps `concurrently`, `tailwindcss` (the latter consumed
  via the Vite plugin — a Knip blind spot); 3 unused exports (`saveMapPreset`,
  `listImportableFiles`, `parseParameterNames`).
- **CSpell:** ~49 findings, mostly terse engine identifiers worth a glance
  (`nnbrs`, `ewtopper`, `lonop`, `Accum`).
- **Unicode dashes:** ~594 occurrences across 165 code files (almost all in
  comments), to be cleared by bounded folder passes — see
  `unicode_and_hygiene_standards.md` §8 for the target order.

---

## 6. Staged rollout order

The order is chosen so each slice lands on a known-green base and adds one
new gate. No slice changes engine `.ts` unless it has to.

| Order | Slice | Adds | Promotes to `quality:ts` |
|---|---|---|---|
| **#250 (this)** | Foundation | Architecture doc + `quality:ts` umbrella | `tsc:game` |
| **#251 (this)** | Strictness ratchet | Check-only `tsconfig.strict.json` + `tsc:strict` report lane (engine config first) | (still `tsc:game`) |
| #252 | ESLint + typescript-eslint | `eslint.config.mjs`, lint-only `tsconfig.eslint.json`, `lint:ts` + `lint:ts:fix` scripts (report-only) | `lint:ts` — promotes once findings cleared |
| #253 | Biome | `biome.json`, `format:ts`, `format:ts:check` scripts | `format:ts:check` — promotion deferred, see §10 |
| #254 | Knip + CSpell + Unicode policy | `knip.json`, `cspell.json`, `.cspell/` dictionary, `hygiene:ts` / `hygiene:unicode` scripts, `unicode_dash_audit.py`, `unicode_and_hygiene_standards.md` | (advisory only) |
| #255 | Unicode bounded rollout | folder-by-folder `--fix` passes via the #254 tool | (advisory only) |
| later | `docs:ts:check` debt | Backfill engine + test docblocks | `docs:ts:check` |

Each slice's PR is expected to keep the umbrella green at every phase. If a
slice can't, it splits — landing the tool with a starter ruleset first, then
ratcheting the rules in a follow-up.

---

## 7. Handoff to implementation sprints

Future slices should reference this document instead of redefining roles.
When picking up #251–#255:

1. Read the matching row in §2 (tool roles) and §6 (rollout order).
2. Add the new script to `package.json` under the canonical name from §3.
3. Wire the new script into `quality:ts` in the same PR if (and only if) it
   lands green over the whole codebase. Otherwise keep it standalone and
   promote in a follow-up.
4. Update §1 (current state) and §5 (known debt) in this file as part of
   the same PR — this doc must stay accurate.

If a slice discovers a new constraint that changes the architecture, update
this doc first, then implement. Don't let the doc rot.

---

## 8. TypeScript strictness ratchet (#251)

This slice introduces a **check-only strict lane** so the compiler starts
catching whole classes of bugs the loose configs hide — without breaking the
emit build and without mass-fixing the errors. Cleanup is a later, separate
effort, done one folder / one error-family at a time.

### 8.1 What landed

- `tsconfig.strict.json` — `extends` `tsconfig.game.json`, overrides
  `strict: true` and `noEmit: true`. It is the engine surface (the production
  hot path) only; it does not emit.
- `npm run tsc:strict` → `tsc -p tsconfig.strict.json`.
- This lane is **non-gating**. It is deliberately NOT in `quality:ts`,
  `tsc:game`, `build`, or `test:all`. The emit build stays `strict: false` and
  green; `tsc:strict` is allowed to print errors. That coexistence is the
  whole point of this slice — see §8.5.

### 8.2 Baseline strict error count (2026-06-16)

`npm run tsc:strict` reports **394 errors** at introduction. That number is the
ratchet's high-water mark: it must only ever go *down*. By error family:

| Errors | TS codes | Strict flag responsible |
|---|---|---|
| 265 | TS7006, TS7005, TS7034, TS7053, TS7009 | `noImplicitAny` |
| 121 | TS18048, TS18047, TS2345, TS2322, TS2532, TS2531, TS2538 | `strictNullChecks` |
| 7 | TS2683 | `noImplicitThis` |
| 1 | TS2339 | (general, surfaces once strict is on) |

The two big families (`noImplicitAny` = 67%, `strictNullChecks` = 31%)
dominate, which sets the rollout order below.

### 8.3 Staged flag rollout order

Enable one flag at a time in the check lane, drive its error family to zero,
then move to the next. Earlier steps unblock later ones (fixing implicit
`any` reveals real null-flow), so order matters:

1. **`noImplicitAny`** (265 errors) — biggest family, mostly untyped function
   parameters and a few untyped local arrays. Largely mechanical: add the type
   the call sites already imply. Start here.
2. **`strictNullChecks`** (121 errors) — the highest-value step for catching
   real bugs (the `string | undefined → string` and possibly-null DOM lookups).
   Requires judgement (guard vs. assert vs. default), so it follows the
   mechanical pass.
3. **`noImplicitThis`** (7 errors) — tiny tail; clean up the few `this` typings.
4. **Full `strict: true`** — already the state of `tsconfig.strict.json`. Once
   the families above are zero, the remaining strict sub-flags
   (`strictFunctionTypes`, `strictBindCallApply`, `alwaysStrict`,
   `strictPropertyInitialization`) should already be satisfied; confirm green.

Only after the check lane is fully green for the engine surface does the
**emit** config (`tsconfig.game.json`) flip `strict: true` — that promotion is
a separate follow-up PR, not this slice.

### 8.4 First cleanup target directories

Strict errors are concentrated; clearing the worst files removes most of the
count. By file (engine `resources/game/script/`), the first cleanup targets:

| Errors | File | Why first |
|---|---|---|
| 82 | `building.ts` | Largest single concentration |
| 76 | `harvest.ts` | Second largest; harvest FSM hot path |
| 59 | `grid.ts` | Core geometry used everywhere |
| 24 | `script.ts` | Engine entry/bootstrap |
| 23 | `clickndragbox.ts` | Selection input |
| 22 | `sprite.ts` | Shared by all renderers |

These six files hold **286 of 394** errors (73%). Clearing them in order
collapses the ratchet fastest. The long tail (`minimap.ts`, `selection.ts`,
`gameMenu.ts`, `collision.ts`, `resources.ts`, and ~15 sync/command modules
with ≤12 each) follows.

### 8.5 Folder-by-folder ratchet workflow

How to ratchet down without ever flipping the gating build red:

1. Pick one file (or one error family within a file) from §8.4.
2. Fix only those errors. Run `npm run tsc:strict` — confirm the total dropped
   and you introduced no new code.
3. Run the gating chain unchanged: `npm run tsc:game`, `npm run build`,
   `npm test`, `npm run quality:ts` must all stay green.
4. Commit with the new strict-error count in the message (the ratchet only
   moves down).
5. When `tsc:strict` reaches **0** for the engine surface, flip
   `tsconfig.game.json` to `strict: true`, delete `tsconfig.strict.json`, point
   `tsc:strict` at the editor config (`tsconfig.json`) for the next surface, or
   retire the script — whichever the follow-up issue decides.

The ratchet rule: **the `tsc:strict` count is a monotonically decreasing
budget.** A PR may lower it; a PR must never raise it. (A future #252 ESLint
gate or a CI step can enforce the ceiling once the count is small enough to be
worth pinning.)

### 8.6 Coexistence guarantee

The emit build is provably untouched by this slice: `tsconfig.game.json`,
`tsconfig.json`, `tsc:game`, `build`, `quality:ts`, and `test:all` are all
unchanged. The only additions are a new file (`tsconfig.strict.json`) and a
new script (`tsc:strict`) that nothing else references. The strict lane can
report its 394 errors indefinitely while the green build ships — until cleanup
retires the gap.

---

## 9. Type-aware ESLint (#252)

This slice introduces ESLint + typescript-eslint as a **non-gating report** so
common TypeScript bug patterns (dropped promises, mis-wired async handlers,
non-exhaustive switches) become machine-detectable, and project-convention
violations (`?:`, committed `console.*`, `any`) get a running count. It does
**not** fix any findings and does **not** edit engine `.ts` to satisfy a rule.

### 9.1 What landed

- `eslint.config.mjs` — flat config. One global-ignore block (generated,
  vendored, plain-JS glue, tooling configs) and one typed block over
  `resources/game/**/*.ts` and `resources/js/**/*.{ts,tsx}`. Rule set and the
  autofix-safe / review-required split are in §2.3 and annotated inline in the
  config.
- `tsconfig.eslint.json` — a **lint-only** TypeScript program. The build configs
  do not cover `resources/js/**` (Vite builds the React editor; it is in no
  tsconfig `include`), so type-aware rules need a dedicated program that spans
  the whole owned surface. It extends `tsconfig.json`, forces `noEmit`, and adds
  `jsx` so the editor `.tsx` parses. Nothing but ESLint references it.
- `npm run lint:ts` → `eslint resources/game resources/js` (report).
- `npm run lint:ts:fix` → the same with `--fix` (autofix-safe rules only).
- This lane is **non-gating**: deliberately NOT in `quality:ts`, `build`, or
  `test:all`. It is allowed to print findings — see §9.4.

### 9.2 Baseline finding count (2026-06-17)

`npm run lint:ts` reports **368 findings (44 errors + 324 warnings)** at
introduction. Errors flag genuine bugs; warnings are convention debt cleaned up
later. By rule:

| Count | Severity | Rule | Family |
|---|---|---|---|
| 223 | warn | `no-ternary` | project convention (`?:` banned) |
| 64 | warn | `no-console` | project convention (no committed `console.*`) |
| 37 | warn | `@typescript-eslint/no-explicit-any` | type hygiene |
| 23 | error | `@typescript-eslint/no-floating-promises` | async bug |
| 13 | error | `@typescript-eslint/no-misused-promises` | async bug |
| 8 | error | `eqeqeq` | autofix-safe (`==` → `===`) |
| 0 | error | `@typescript-eslint/switch-exhaustiveness-check` | (none today; guards future) |
| 0 | error | `no-implicit-coercion` | autofix-safe (none today) |

The **44 errors** are the high-value lane: the 36 promise findings are the most
likely real defects (fire-and-forget `fetch` in the sync modules, async
functions handed to event handlers), and the 8 `eqeqeq` are mechanically
fixable.

### 9.3 First cleanup target directories

By file, the heaviest concentrations (clear these first to collapse the count
fastest):

| Findings | File | Surface |
|---|---|---|
| 47 | `resources/js/editor/MapEditor.tsx` | editor |
| 42 | `resources/game/script/script.ts` | engine entry/bootstrap |
| 39 | `resources/game/script/harvest.ts` | engine (harvest FSM) |
| 27 | `resources/game/script/building.ts` | engine |
| 21 | `resources/game/script/hud.ts` | engine |
| 20 | `resources/game/script/saveState.ts` | engine |
| 20 | `resources/game/script/buildingCommands.ts` | engine |

Recommended cleanup order, independent of file: (1) `eqeqeq` (autofix, 8 — run
`lint:ts:fix`), (2) the 36 promise errors by hand (real bugs), (3) `no-console`
(route through `errorReporter`), (4) `no-ternary` and `no-explicit-any` as the
long convention tail. Each cleanup PR drives the count down and keeps the gating
chain green; the lane promotes into `quality:ts` only once the error count is
zero (warnings can ratchet behind `--max-warnings`).

### 9.4 Coexistence guarantee

The emit build is provably untouched by this slice: `tsconfig.game.json`,
`tsconfig.json`, `tsc:game`, `build`, `quality:ts`, and `test:all` are all
unchanged. The only additions are two files (`eslint.config.mjs`,
`tsconfig.eslint.json`), two scripts (`lint:ts`, `lint:ts:fix`), and the
`eslint` + `typescript-eslint` devDependencies. Nothing in the gating chain
references them, so `lint:ts` can report its 368 findings indefinitely while the
green build ships — until cleanup retires them.

---

## 10. Biome formatter (#253)

This slice gives TypeScript a single canonical formatter and import-sorter, the
same way #251 gave it a single strictness lane. It follows the same discipline:
**introduce the tool, measure the drift, do not mass-reformat, do not gate.**
The code is reformatted later, folder-by-folder, the same way strict errors are
retired.

### 10.1 What landed

- `@biomejs/biome` (dev dependency) + `biome.json` configured as a **formatter
  only** — `linter.enabled: false`, so it owns formatting and import order and
  nothing else (the linter is ESLint's job, #252; this prevents the two tools
  from fighting over the same lines).
- `npm run format:ts:check` → `biome check resources/game resources/js`
  (report-only; prints the drift, changes nothing, exits non-zero when drift
  exists).
- `npm run format:ts` → `biome check --write resources/game resources/js`
  (applies formatting + import sorting in place).
- Both scripts run `biome check` (not `biome format`) on purpose: import
  sorting is a Biome *assist* action that `biome format` skips. With the linter
  disabled, `biome check` resolves to formatter + assist only.
- This pair is **non-gating**. It is deliberately NOT in `quality:ts`,
  `tsc:game`, `build`, or `test:all`. The build stays green; `format:ts:check`
  is allowed to report drift. That coexistence is the whole point of this slice
  — see §10.5.

### 10.2 Config decisions

`biome.json` is tuned to the **existing** house style so that adoption is a
no-op for code that already conforms, and so a future rollout produces the
smallest possible diff:

| Option | Value | Why |
|---|---|---|
| `indentStyle` / `indentWidth` | space / 4 | Matches the engine and editor TS already in the tree. |
| `javascript.quoteStyle` | single | The codebase is ~99% single-quoted. |
| `semicolons` | always | Existing code is fully semicolon-terminated. |
| `trailingCommas` | all | Already the prevailing style in multi-line literals. |
| `lineWidth` | 100 | Wide enough to leave most existing lines un-wrapped (default 80 would re-wrap far more). |
| `lineEnding` | lf | Repo is LF. |
| `linter.enabled` | false | ESLint owns correctness; Biome owns formatting (§2.4). |
| `assist.organizeImports` | on | Import order is Biome's per §2.4 (engine has no imports; affects editor/test files). |

Scope (`files.includes`): `resources/game/**` and `resources/js/**` only.
Excluded: `public/**` (the **compiled** engine JS — Biome must never touch the
`tsc` output), `vendor/**`, `node_modules/**`, `storage/**`.

### 10.3 Baseline drift (2026-06-18)

`npm run format:ts:check` reports **69 of 76 files** would be reformatted at
introduction (plus 5 files with import-order fixes — 74 findings total). By
surface:

| Drift | Surface | Notes |
|---|---|---|
| 63 of 68 | engine `resources/game/**` | The bulk; reformat folder-by-folder. |
| 6 of 6 | editor `resources/js/**` | Small, self-contained — a good first rollout target. |

This is the formatter's high-water mark, the analogue of §8.2's 394 strict
errors. It only ever goes *down* as folders are reformatted.

### 10.4 Bounded rollout rules

Reformatting 69 files in one commit would bury every future `git blame` and
collide with in-flight branches. Roll out in bounded passes instead:

1. **One folder (or one file) per PR.** Run `npm run format:ts` scoped to that
   path, commit only those files, with the reformat called out in the message.
2. **Reformat-only commits stay pure** — never mix a Biome reformat with a
   behaviour change in the same commit, so review and `git blame` stay legible.
3. **The gating chain must stay green** across the reformat: `npm run tsc:game`,
   `npm run build`, `npm test` must pass unchanged (formatting is cosmetic, so
   they will).
4. **Editor TS first** (`resources/js/**`, 6 files) — smallest surface, real
   modules, exercises import sorting. Engine TS follows, highest-traffic files
   last to minimise branch collisions.
5. **Promote to `quality:ts` only when drift reaches zero.** When
   `format:ts:check` is green over the whole scope, add `&& npm run
   format:ts:check` to `quality:ts` (and slot it into `test:all` after
   `tsc:game`) in a one-line follow-up PR. Until then it is a standalone report,
   exactly like `tsc:strict`.

The rollout rule mirrors the ratchet: **`format:ts:check`'s drift count is a
monotonically decreasing budget.** A PR may lower it; a PR must never raise it.

### 10.5 Interaction with ESLint and Night Shift

- **ESLint (#252):** no overlap by construction. Biome's linter is disabled, so
  Biome only ever changes whitespace and import order; ESLint only ever reports
  correctness rules and is configured to defer all formatting to Biome (§2.3).
  Run order when both land: `tsc` → `lint:ts` (semantics) → `format:ts:check`
  (cosmetic).
- **Night Shift:** `format:ts` is safe to run unattended (`biome check --write`
  is deterministic, non-interactive, and only rewrites cosmetics). The
  autonomous agent may run a **bounded** `format:ts` pass over one folder as a
  maintenance job, following §10.4 — never a repo-wide reformat in a single
  commit, and never mixed with a feature change.

### 10.6 Coexistence guarantee

The emit build is provably untouched by this slice: no `.ts` source was
reformatted, and `tsconfig.game.json`, `tsc:game`, `build`, `quality:ts`, and
`test:all` are all unchanged. The only additions are a new file (`biome.json`),
a new dev dependency (`@biomejs/biome`), and two scripts (`format:ts`,
`format:ts:check`) that nothing else references. Biome can report its 69-file
drift indefinitely while the green build ships — until the bounded rollout
retires it.
