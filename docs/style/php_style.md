# PHP Coding Style and Commenting Conventions (Project Standard)

This document defines the required PHP coding style for AgileMedievalPeasantBoard
application code, Livewire components, tests, migrations, seeders, factories,
and related tooling.
The core goal is clarity, explicitness, and long-term maintainability.

---

## Core Philosophy

- Code must be readable first and clever second.
- Explicit behavior is preferred over compact tricks.
- Descriptive names are required for variables, functions, and files.
- Future readers should understand intent without external context.
- Runtime paths should be straightforward to trace and debug.

---

## Standards Baseline

This project follows these PHP conventions:

- PSR-12 coding standard baseline.
- Modern PHP semantics with strict type hinting for parameters and return types.
- Explicit visibility (`public`, `protected`, `private`) on all class members.
- Consistent formatting with 4 spaces for indentation.

---

## Naming Conventions (Locked)

### Variables and Properties

- Use `$camelCase`.
- Use descriptive multi-word names (e.g., `$extractedPayload`).
- Never use single-letter variable names except conventional short values (e.g., `$i` in loops).

### Functions and Methods

- Use `camelCase`.
- Function names must be verb-based and explicit.
- Avoid abbreviations and generic names.

---

## Commenting Rules (Critical)

### Comment Density

- **CRITICAL REQUIREMENT:** Add a meaningful comment (1 or more comments) every 3 logical lines or less in all execution paths. This explicitly applies to test code as well.
- Explain intent, expectations, and constraints, not obvious syntax.
- Prioritize *why* over *what*.

This requirement is about preserving intent, not padding files. Good comments explain
gameplay rules, Livewire state boundaries, deployment constraints, security assumptions,
test setup, and failure handling. Do not add filler comments that merely repeat syntax,
and prefer clearer names or smaller methods when the code itself is hard to follow.

### DocBlocks

- Use standard PHPDoc blocks for all classes and methods.
- If there is a parameter or return type it must be documented in the DocBlock, even if it is already type-hinted in the signature. This ensures that all relevant information is visible in IDEs and documentation generators without needing to inspect the code.
- Include a description of the method's purpose, parameters, return value, and any exceptions thrown.
- DocBlocks should be concise but informative, focusing on the purpose and behavior of the code.

### Functions

- If a function or method has parameters, document each parameter with `@param`.
- Leave out `@return void`, but include `@return` for every non-void return value.
- Use one empty line between the description and tags.
- Use one empty line between `@param` tags and the `@return` tag.

### Inline Comments

- Use line comments strategically to break down blocks of statements and explain assertions.

---

## Forbidden Operators

### Ternary (`?:`)
Instead consider using a function or an explicit if statement to handle the logic. This makes the code more readable and easier to debug.

### Null Coalescing (`??`)

The null coalescing operator `??` is **forbidden** in this project.

It silently collapses two distinct cases : key absent and key present but null : into a
single fallback, hiding the reason a default was reached. Both cases must be handled
explicitly using `array_key_exists`, `isset`, or a direct null comparison so the intent
is visible to every future reader.

Bad:
```php
$workerId = (int) ($payload['worker_id'] ?? 0);
```

Good:
```php
if (!array_key_exists('worker_id', $payload)) {
    return;
}
$workerId = (int) $payload['worker_id'];
```

---

## Boolean Conditionals

### Explicit Boolean Comparisons

When a method, function, or property is already known to be a `bool`, prefer
explicit boolean comparisons over shorthand negation in conditionals.

This keeps the condition honest about the type being checked and avoids making
the reader mentally infer whether the value might be truthy/falsy instead of a
real boolean.

Preferred:

```php
if ($this->hasActiveSession() === false) {
    return;
}
```

Allowed when checking for true:

```php
if ($user->isAdmin() === true) {
    // ...
}
```

Avoid:

```php
if (! $this->hasActiveSession()) {
    return;
}
```

This rule is especially important for `has*`, `can*`, `is*`, and similar methods
that already advertise a boolean contract in their names and type signatures.

---

## Final Rule

If a future reader must guess intent, the code is wrong.
Baseline compliance is required.
Clarity is the priority.
