# JavaScript / Node Coding Style and Commenting Conventions (Project Standard)

This document defines required JavaScript and Node.js coding style for ArcaneArcadeMachineFactory runtime and tooling.

The goal is clarity, explicitness, and long-term maintainability.

---

## Core Philosophy

- Code must be readable first and clever second
- Explicit behavior is preferred over compact tricks
- Descriptive names are required for variables, functions, and files
- Future readers should understand intent without external context
- Runtime paths should be boring, predictable, and easy to debug

---

## Standards Baseline

This project follows these JavaScript conventions:

- Modern ECMAScript modules where practical (`import` / `export`)
- Strict mode behavior through module execution semantics
- Consistent formatting with 4 spaces for indentation

Where JavaScript standards are silent, this document defines project-specific rules.

---

## Naming Conventions (Locked)

### Variables and Properties

- Use `camelCase`
- Use descriptive multi-word names
- Never use single-letter variable names except conventional short callback names only when obvious (`err` is still discouraged)

Good:

```js
const decodedRequestPayload = JSON.parse(rawRequestBody);
const blockerRegistryPath = resolveBlockerRegistryPath(factoryRoot);
```

Bad:

```js
const d = JSON.parse(raw);
const tmp = getPath();
```

### Constants

- Use `UPPER_SNAKE_CASE` for true constants
- Prefer `const` for all values that do not change

Good:

```js
const EVENT_STREAM_FILE_NAME = "events.jsonl";
```

### Functions

- Use `camelCase`
- Function names must be verb-based and explicit
- Avoid abbreviations and generic names

Good:

```js
function enqueueHeightmapJob() {}
function validateRequestPayload() {}
function emitScrumBlockerClearEvent() {}
```

Bad:

```js
function doStuff() {}
function handle() {}
function proc() {}
```

---

## File Structure Rules

- One responsibility per file
- Avoid mixing transport, domain logic, and formatting in the same function
- Keep I/O boundaries explicit
- Keep side effects near entry points

Example:

- `scrum_master_review.mjs`
  - Read blocker artifacts
  - Build summaries
  - Write review report
  - Print operator output

Nothing more.

---

## Commenting Rules (Critical)

### Comment Density

- Add a meaningful comment every 3 to 4 logical lines in runtime-critical paths
- Explain intent and constraints, not obvious syntax
- Prioritize why over what

### Block Comments

Use block comments for purpose and constraints:

```js
/**
 * Emits one blocker-clear event only when an open blocker exists.
 *
 * This prevents false clear signals and keeps blocker lifecycle
 * replayable from canonical event history.
 */
```

### Inline Comments

```js
// Reuse existing blocker id so raise/clear linkage remains stable across retries.
const blockerId = existing.blockerId || deriveBlockerId(stage, jobId, reason);
```

### Guard Clauses Must Be Commented

```js
// Reject empty payloads early to avoid writing invalid event records.
if (!rawRequestBody || rawRequestBody.trim() === "") {
    throw new Error("Empty request body");
}
```

---

## Error Handling Rules

- Fail fast and explicitly
- Never swallow errors silently
- Use guard clauses before deep nesting
- Include enough context in errors for operator triage

Good:

```js
if (!fs.existsSync(sourcePath)) {
    throw new Error(`Missing source file: ${sourcePath}`);
}
```

---

## JSON Handling

- Parse JSON inside guarded try/catch blocks
- Validate shape before use
- Write stable JSON for artifacts (`JSON.stringify(payload, null, 2)`)
- Never trust incoming JSON without validation

---

## Formatting Rules

- 4 spaces per indentation level
- No tabs
- One statement per line
- Blank lines between logical sections
- Always use braces for `if`, `for`, and `while`
- Prefer trailing commas in multiline literals for cleaner diffs

---

## Forbidden Practices

- Single-letter variable names
- Clever one-liners that hide intent
- Deeply nested conditionals when guards are possible
- Implicit side effects
- Mixing file I/O and business rules in the same function
- Silent catch blocks

---

## Canonical Node Example

```js
#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

const HEIGHTMAP_INBOX_DIRECTORY = "/app/Heightmap/inbox";

// Read stdin payload once at process start.
const rawRequestBody = fs.readFileSync(0, "utf8");

// Reject empty payloads to prevent invalid job files.
if (!rawRequestBody || rawRequestBody.trim() === "") {
    throw new Error("Empty request body");
}

let decodedRequestPayload;

// Parse JSON in a guarded block so malformed payloads fail explicitly.
try {
    decodedRequestPayload = JSON.parse(rawRequestBody);
} catch (parseError) {
    throw new Error(`Invalid JSON payload: ${String(parseError)}`);
}

// Generate unique identifiers to avoid file collisions.
const timestampPrefix = new Date().toISOString().replace(/[:.]/g, "-");
const randomSuffix = Math.random().toString(16).slice(2, 10);
const jobIdentifier = `${timestampPrefix}_${randomSuffix}`;

// Build payload as a stable, explicit object.
const jobPayload = {
    job_id: jobIdentifier,
    requested_at_utc: new Date().toISOString(),
    payload: decodedRequestPayload,
};

const jobFilePath = path.join(HEIGHTMAP_INBOX_DIRECTORY, `${jobIdentifier}.json`);

// Persist prettified JSON for operator readability and diffs.
fs.writeFileSync(jobFilePath, JSON.stringify(jobPayload, null, 2) + "\n", "utf8");

process.stdout.write(
    JSON.stringify(
        {
            ok: true,
            job_id: jobIdentifier,
        },
        null,
        2,
    ) + "\n",
);
```

---

## Final Rule

If a future reader must guess intent, the code is wrong.

Baseline compliance is required.
Clarity is the priority.
