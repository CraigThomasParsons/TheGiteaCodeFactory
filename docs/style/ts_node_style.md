# TypeScript / Node Coding Style and Commenting Conventions

This guide merges the project standard for explicit, heavily documented code
with the public Google TypeScript Style Guide:

- https://google.github.io/styleguide/tsguide.html

The goal is readable, predictable TypeScript that a future maintainer can
debug without reconstructing hidden assumptions.

## Core Philosophy

- Code must be readable first and clever second.
- Explicit behavior is preferred over compact tricks.
- Descriptive names are required for variables, functions, files, and types.
- Future readers should understand intent without external context.
- Runtime paths should be boring, predictable, and easy to debug.
- Types should document contracts; comments should document intent and constraints.

## Source File Structure

Use this order when the section exists:

1. Copyright or license JSDoc.
2. File-level JSDoc with `@fileoverview` when the file has non-obvious responsibilities.
3. Imports.
4. Type and interface declarations.
5. Constants.
6. Implementation.
7. Export or global registration.

Separate present sections with exactly one blank line.
Seperate functions and classes with one blank line before and after.

## Formatting Rules

- Use UTF-8 source files.
- Use 4 spaces per indentation level.
- Use semicolons; never rely on automatic semicolon insertion.
- Use one statement per line.
- Use braces for every `if`, `for`, `while`, and callback block.
- Prefer trailing commas in multiline literals when the local formatter accepts them.
- Keep generated JavaScript out of hand edits; edit TypeScript source and regenerate.

## Imports And Exports

- Use ES module imports and exports for module code.
- Prefer named imports for frequently used symbols.
- Prefer namespace imports when many symbols from a large API would otherwise clutter names.
- Use `import type` for type-only imports when working in module files.
- Use named exports; avoid default exports.
- Minimize the exported API surface.
- Do not export mutable bindings. Use explicit getter or setter functions when shared mutable state is required.

Legacy browser files in this project may use global IIFEs because `tsconfig.game.json`
compiles with `module: "none"`. Those files must still expose a narrow, documented
global API and keep implementation details private to the IIFE.

## Naming Conventions

- Use `camelCase` for variables, functions, methods, and properties.
- Use `PascalCase` for classes, interfaces, type aliases, and enums.
- Use `UPPER_SNAKE_CASE` only for true constants.
- Use descriptive names; do not abbreviate by removing letters.
- Avoid single-letter identifiers except tiny local callback variables where the meaning is unmistakable.
- Do not prefix interfaces with `I`.
- Do not encode types in names when TypeScript already expresses that information.

## Type Rules

- Prefer `interface` for object and JSON shapes.
- Use type aliases for unions, primitives, tuples, or repeated complex expressions.
- Prefer `unknown` over `any`.
- Avoid `any`; if it is unavoidable, add a short comment explaining why a narrower type is impossible.
- Prefer optional properties and parameters (`?`) over explicit `| undefined`.
- Use structural types intentionally and annotate object literals when they implement an important contract.
- Rely on inference for trivial literals and `new` expressions, but annotate function returns and public contract values.
- Use `as` assertions only when a runtime check or surrounding invariant makes the assertion safe.
- Do not use angle-bracket assertions.
- Do not use `@ts-ignore`, `@ts-expect-error`, or `@ts-nocheck`.
- Do not use double-negation boolean coercion. Use `Boolean(value)` only when intentionally converting a value to a boolean, and prefer explicit domain checks such as `unitId !== ''` when validating ids or payload fields.

Good:

```ts
const hasUnitSelection = unitIds.some(function(unitId: string): boolean {
    return unitId !== '';
});

const shouldShowPanel = Boolean(selectedElement);
```

Bad: compact boolean-coercion punctuation that hides whether the code is
checking an id, a nullable object, or a numeric value.

## Function Rules

- Use function declarations for named top-level and IIFE-local functions.
- Use arrow functions for callbacks, especially when forwarding exact callback arguments.
- Do not pass functions like `parseInt` directly as callbacks when optional parameters could leak through.
- Prefer guard clauses over deeply nested conditionals.
- Comment guard clauses when the reason is not immediately obvious.
- Use default parameters sparingly; prefer an options object when a function has several optional inputs.
- Keep side effects near entry points and make state mutation explicit.

## Comments And JSDoc

- Add meaningful comments every 3 to 4 logical lines in runtime-critical paths.
- Explain why, constraints, invariants, and failure behavior; do not narrate obvious syntax.
- Use JSDoc (`/** ... */`) for file responsibilities, public APIs, interfaces, classes, and non-trivial helpers.
- Use line comments (`// ...`) for implementation details inside functions.
- Do not put TypeScript type annotations inside JSDoc `@param` or `@returns`; TypeScript already owns those types.
- Add `@deprecated` with clear migration instructions when deprecating an API.

Good:

```ts
/**
 * Builds a stable save payload from runtime modules.
 *
 * The payload must stay compatible with Laravel persistence and future load
 * hydration, so empty v1 sections are emitted instead of omitted.
 */
function exportSnapshot(options: SaveSnapshotOptions = {}): RtsSaveSnapshot {
    // Units are exported once and reused by orders so both sections agree.
    const unitSnapshots = exportUnits();

    return {
        schema_version: CURRENT_SCHEMA_VERSION,
        entities: {
            units: unitSnapshots,
        },
    };
}
```

Bad:

```ts
function go(o: any) {
    // Gets data.
    return o.x;
}
```

## Error Handling Rules

- Fail fast and explicitly.
- Never swallow errors silently.
- Include enough context in thrown errors or console warnings for triage.
- Validate external JSON before reading nested fields.
- Prefer runtime checks over unsafe assertions.

### Invariant guards: `RTS.required`

Distinguish two kinds of `if (!x) { return; }` guard:

- **Legitimate "nothing to do"** — `x` may validly be absent (nothing selected,
  an entity that has died, an off-map tile). Keep the plain `return`.
- **Broken invariant** — `x` is something the code's own logic guarantees should
  exist (a required DOM singleton like `#main` / `#command-frame`, a required
  global, a required data structure). Returning silently hides real breakage;
  use `RTS.required` instead:

```ts
const main = document.getElementById('main');
if (!window.RTS.required(main, 'building.pageToTile: #main missing')) {
    return;
}
main.getBoundingClientRect(); // `main` is narrowed to HTMLElement here
```

`RTS.required(value, context)` keeps the non-fatal early-return but logs
`console.error` (caught by the Laravel Dusk smoke test's SEVERE-console assertion
and shown in DevTools), de-duped per `context`. It is a type guard, so callers
keep TypeScript narrowing. Only `null`/`undefined` count as missing — a
legitimate `0`, `''`, or `false` is treated as present.

## Browser Runtime Rules

- Treat DOM, `window`, `dataset`, and server-injected globals as external input.
- Parse dataset values through guarded helpers before using them as numbers.
- Keep global namespace additions narrow, documented, and attached in one place.
- Do not modify built-in prototypes or constructors.
- Do not use `eval`, `Function(string)`, `with`, `debugger`, or non-standard runtime features.
- Use stable JSON shapes for save files and API payloads.

## Testing Rules

- Tests follow the same comment and naming rules as runtime code.
- Test names should describe behavior and expected outcome.
- Avoid `@ts-ignore`; fix the type surface or use a typed helper.
- Stub external modules with typed partial objects when full runtime boot is unnecessary.
- Prefer focused tests for serialization, persistence, and state transitions.

## Forbidden Operators

### Ternary Operator (`? :`)

The ternary operator is **forbidden** in this project.

Ternary expressions collapse conditional logic into a single line, forcing readers
to parse the branch meaning inline rather than reading it as a clear condition and
assignment. Use an explicit `if` block instead so the two cases are visually separated
and individually commented.

Bad:
```ts
const amount = raw ? parseInt(raw, 10) : null;
```

Good:
```ts
let amount: number | null = null;
if (raw) {
    amount = parseInt(raw, 10);
}
```

---

## Final Rule

If a future reader must guess intent, the code is wrong.

Baseline compliance is required. Clarity is the priority.
