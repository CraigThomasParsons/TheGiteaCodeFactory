# Unicode & Hygiene Standards

> **Example guide.** Written for AgileMedievalPeasantBoard; issue numbers, paths and game vocabulary refer to that repository; included as a worked example. Copy it into your
> project and replace the project-specific parts. See [README.md](README.md).

How this repo handles ambiguous Unicode characters and code hygiene (dead code,
unused dependencies, spelling). Written 2026-06-20 as the deliverable of issue
#254 (Phase 12D — Developer Tooling & Code Quality), slice 5 of the TS quality
track. It is the companion to `typescript_quality_architecture.md` (which owns
the *roles* of every check) — this doc is the *operating manual* for the two
hygiene concerns: ambiguous Unicode and Knip/CSpell.

**Everything in this doc is advisory.** None of it gates a PR. The point is to
make cleanup *intentional and bounded* instead of ad hoc, so Night Shift (or a
human) can run safe, reviewable passes.

---

## TL;DR

| Concern | Tool | Posture | How to run |
|---|---|---|---|
| Ambiguous Unicode dashes | `scripts/tools/unicode_dash_audit.py` | Advisory; bounded `--fix` | `npm run hygiene:unicode` |
| Dead code / unused exports / deps | Knip (`knip.json`) | Advisory | `npm run hygiene:ts` |
| Spelling in source | CSpell (`cspell.json` + `.cspell/`) | Advisory | `npm run hygiene:ts` |

- `npm run hygiene:ts` runs Knip then CSpell. Non-gating — a non-zero exit on
  findings is informational, not a build failure.
- `npm run hygiene:unicode` audits ambiguous dashes (never mutates).
- Markdown prose **keeps** its em dashes — the dash policy is a *code* policy.

---

## 1. The ambiguous-Unicode problem, measured

The #254 Phase 1 audit (2026-06-20) found the problem is **narrow and
well-defined**, not a sprawling mess:

- **Exactly two** ambiguous dash codepoints exist anywhere in the repo:
  - `U+2014 EM DASH` `—` — 1919 occurrences
  - `U+2013 EN DASH` `–` — 352 occurrences
- **No** minus-sign (`U+2212`), non-breaking hyphen (`U+2011`), figure dash
  (`U+2012`), horizontal bar (`U+2015`), or fullwidth hyphen (`U+FF0D`).
- The bulk (≈1600) live in `docs/**` Markdown prose, where they are **correct**
  and stay.
- In code files, 594 occurrences across 165 files — **almost entirely inside
  comments**. The only occurrence inside an actual code token is in vendored,
  minified jQuery UI (`public/game/js/jquidragcollide.min/**`), inside a regex
  character class `[^\-:–\s]` — which we do **not** edit.

Why "ambiguous" matters: an em/en dash sitting where a reader expects an ASCII
hyphen-minus is a footgun in code — it can silently break a CLI flag, a regex,
a string key, or an identifier, and it is invisible in most editors. In prose it
is simply typography. Hence the policy below splits on **file class**, not on
character.

### Codepoint → ASCII mapping (the only transform we make)

| Codepoint | Char | Replacement | Rationale |
|---|---|---|---|
| `U+2014` EM DASH | `—` | `-` | Spaced ` — ` becomes ` - `; unspaced `a—b` becomes `a-b` (reads as a hyphenated compound) |
| `U+2013` EN DASH | `–` | `-` | Numeric/range dashes become ASCII hyphen |

The tool changes **nothing else** — it touches only these two codepoints and
leaves every other byte untouched.

---

## 2. The Unicode normalization policy

1. **Code files are ASCII-dash only.** In `.ts .tsx .js .mjs .php .py .sh
   .css`, em/en dashes are normalized to `-`. This is mechanical and safe
   because they appear only in comments.
2. **Markdown / prose keeps its em dashes** (`docs/**`, `*.md`). This is the
   allowed exception. Do not "normalize" prose — it would be a pointless,
   enormous, review-hostile diff.
3. **Vendored, minified, and compiled output is never touched** — even if
   explicitly targeted. The hard-exclusion list:
   - `node_modules/`, `vendor/`
   - `public/game/js/**` (vendored + minified jQuery UI)
   - `public/game/script/**` (compiled engine output — fix the `.ts` **source**
     in `resources/game/script/**` and rebuild; never hand-edit the output)
   - `public/build/**`, `storage/**`, `bootstrap/cache/**`
   - any `**/*.min.*`
4. **Only git-tracked files** are ever considered.
5. **JSON is left alone** by default — values may legitimately carry prose.

### Safe vs review-required file classes

| Class | Examples | Posture |
|---|---|---|
| **Safe (mechanical `--fix`)** | engine/editor TS comments, PHP/Python/shell comments, CSS comments | Bounded `--fix` per folder, then eyeball the diff |
| **Leave as-is** | `docs/**` Markdown prose | Em dashes are correct prose |
| **Never touch** | `public/game/js/**`, `vendor/**`, `**/*.min.*`, `public/game/script/**` | Hard-excluded by the tool |

---

## 3. The mechanical workflow tool

`scripts/tools/unicode_dash_audit.py` is the bounded, reviewable normalizer.
Run it with `/usr/bin/python3` (the default `python3` is a uv shim).

```bash
# Audit everything (advisory; always exits 0):
/usr/bin/python3 scripts/tools/unicode_dash_audit.py --check
npm run hygiene:unicode                     # same thing

# Audit one bounded folder (a pass target):
/usr/bin/python3 scripts/tools/unicode_dash_audit.py --check --path resources/game/script

# Apply a bounded, capped, reviewable fix to ONE folder:
/usr/bin/python3 scripts/tools/unicode_dash_audit.py --fix --path resources/game/script --max-files 25
```

Guarantees that make it safe for an autonomous agent:
- `--check` is the default and **never mutates**.
- `--fix` only ever rewrites **code files** within `--path` scope.
- An **unbounded `--fix` is refused** — if the matched set exceeds `--max-files`
  (default 25) the tool exits non-zero and changes nothing. Bounded is the
  whole point.
- The hard-exclusion list (§2.3) is enforced even against an explicit `--path`.
- Only the two mapped codepoints are altered; the tool is a no-op on a file
  that has none.

---

## 4. Knip — dead code / unused exports / unused dependencies

Config: `knip.json`. Run via `npm run hygiene:ts`.

- **Scope:** the **module-based** TypeScript only — the React map editor
  (`resources/js/**`) plus node tooling (`scripts/ts-docblocks/**`).
- **Out of scope:** the engine in `resources/game/script/**`. It is
  `module: none` script-tag globals (`window.RTS.*`; see
  `frontend_architecture.md` §1), so it has **no import graph** for Knip to
  follow. Knip would report every engine module as an unused file, which is
  noise, not signal. Engine dead-code detection waits for the pixi.js/ESM
  migration. This is a known, accepted limitation.
- **Baseline at introduction (advisory):** unused devDependencies
  (`concurrently`, `tailwindcss` — the latter is consumed via the Vite plugin,
  a Knip blind spot), and 3 unused exports (`saveMapPreset`,
  `listImportableFiles`, `parseParameterNames`). These are candidates for a
  future cleanup, not bugs.

Knip owns dead code / unused exports / unused files / unused dependencies. It
does **not** own types, lint rules, formatting, or spelling.

---

## 5. CSpell — spelling in source

Config: `cspell.json`; dictionary: `.cspell/project-words.txt`. Run via
`npm run hygiene:ts`.

- **Language:** `en,en-GB`. This repo writes British English (`behaviour`,
  `colour`, `serialise`, `initialise`) — those are correct, not typos.
- **Scope:** real source (`resources/**/*.{ts,tsx,mjs}` in the script;
  `ignorePaths` in config hard-excludes vendored/minified/compiled output and
  foreign-text reference material — `public/game/js/**`, `public/game/script/**`,
  `docs/mcp/**` LLM dumps, `.agents/skills/**`, `.kiro/**`).
- **Dictionary, not pragmas:** game-domain and stack terms (peasant, blackrock,
  autotile, livewire, gitea, …) and game-lore names (medivh, lothar, …) live in
  `.cspell/project-words.txt`, so the project vocabulary is reviewable in one
  place. Do **not** sprinkle `// cspell:ignore` pragmas through the code.
- **Baseline at introduction (advisory):** ~49 findings — terse engine
  identifiers worth a human glance (`nnbrs`, `ewtopper`, `lonop`, `Accum`,
  `pathability`). Left flagged on purpose: that is exactly the signal CSpell is
  for.

CSpell owns spelling only. Anything the compiler, linter, or formatter owns is
out of its lane.

---

## 6. Advisory vs required

| Check | Today | Promotion path |
|---|---|---|
| `hygiene:unicode` (`--check`) | Advisory | Stays advisory; bounded `--fix` passes shrink the count |
| `hygiene:ts` (Knip + CSpell) | Advisory, non-gating | Promote to a CI gate only after the backlog is cleared |

Why advisory first: flipping a brand-new check to **required** on introduction
either (a) blocks every PR until a large backlog is paid, or (b) gets routed
around with `--no-verify`-style escapes. Both are worse than a visible advisory
job. A check is promoted to gating only once its count is at (or near) zero —
the same ratchet discipline used for the strict lane (`tsc:strict`, doc §8).

---

## 7. Bounded Night Shift passes

The cleanup is designed to be run autonomously **a folder at a time**, never as
one giant rewrite:

1. **Pick one target folder** from §8. Audit it:
   `--check --path <folder>`.
2. **Fix it bounded + capped:** `--fix --path <folder> --max-files 25`. If the
   tool refuses (too many files), the folder is too big for one pass — descend
   into a subfolder.
3. **Re-run the gating chain unchanged:** `npm run tsc:game`, `npm run build`,
   `npm test`, `npm run quality:ts` must all stay green. Dash changes live in
   comments, so they should not move any of these — if one breaks, the pass
   touched something it should not have. Stop and inspect.
4. **Review the diff:** every hunk must be a pure `—`/`–` → `-` swap inside a
   comment or string. Nothing else. Then commit with the folder name and the
   occurrence count in the message.
5. Repeat for the next folder.

A single pass is intentionally small enough to review by eye — that is what
makes it low-risk for an unattended agent.

### Review checks for a Unicode cleanup diff
- Every changed line differs **only** by `—`/`–` → `-` (no reflow, no other
  edits).
- No file under a hard-excluded path appears in the diff.
- No `.md` / `docs/**` prose file appears (those keep their em dashes).
- `git diff --stat` line count ≈ the occurrence count the audit reported.

---

## 8. First cleanup target folders (recorded)

In bounded-pass order, by code-dash density (from the #254 audit):

| Order | Folder | Occurrences | Notes |
|---|---|---|---|
| 1 | `resources/game/script/**` | 58 | Engine source; comments only; ~18 files — split per-file if a pass is refused |
| 2 | `app/**` (Services, Actions, Http, Events, Models) | ~150 | PHP docblocks/comments; run `vendor/bin/pint --dirty` after |
| 3 | `scripts/tools/**` | ~200 | Python tooling comments; `sync_to_gitea.py` is the single biggest file (101) |
| 4 | `database/seeders/**` | ~45 | Inline `//` comments in autotile/map seeders |

`docs/**` is **explicitly not a target** — prose em dashes are correct.

---

## 9. Relationship to the other quality docs

| Doc | Owns |
|---|---|
| `typescript_quality_architecture.md` | The *roles* of every check + rollout order (#250–#255) |
| `ts_node_style.md` / `frontend_architecture.md` | What the *code* looks like / how it's structured |
| `php_style.md` | PHP style (incl. ASCII-only operators `??`/`?:` bans) |
| **this doc** | The *operating manual* for Unicode + Knip/CSpell hygiene |

If a future change alters the policy (a new ambiguous codepoint appears, a new
exclusion is needed, a check is promoted to gating), update this doc **and** the
`typescript_quality_architecture.md` rollout table in the same PR. Do not let
either rot.
