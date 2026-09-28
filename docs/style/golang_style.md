# Golang Coding Style and Commenting Conventions (Project Standard)

This document defines the required Go coding style for Gopher, ThePostalService, and related tooling within the Auralis project.
The primary goal is extreme clarity, explicitness, and long-term maintainability, overriding the traditional Go philosophy of minimal commenting.

---

## Core Philosophy

- Code must be readable first and clever second.
- Explicit behavior is preferred over compact tricks.
- Descriptive names are strictly required for variables, functions, and files.
- **Override to standard Go**: While Idiomatic Go favors extremely short variable names (`rt` for `router`), **we explicitly forbid this**. Use full descriptive names.
- Future readers should understand intent without external context.
- Runtime paths should be boring, predictable, and easy to debug.

---

## Standards Baseline

This project follows these Golang conventions:

- Strict enforcement of `gofmt` and `goimports` formatting.
- Explicit return types and strict error handling (`if err != nil`).
- Proper use of Go contexts (`context.Context`) for all long-running operations.

Where standard Go conventions are flexible or silent, this document defines project-specific rules.

---

## Naming Conventions (Locked)

### Variables and Properties

- Use `camelCase` for unexported variables and properties.
- Use `PascalCase` for exported variables and properties.
- Use descriptive multi-word names.
- **Never** use single-letter variable names except for extremely short-lived loop indices (e.g., `i` in `for i := 0; i < len; i++`).

**Good:**
```go
decodedRequestPayload := json.Unmarshal(rawRequestBody, &target)
blockerRegistryPath := ResolveBlockerRegistryPath(factoryRoot)
```

**Bad:**
```go
decReq := json.Unmarshal(body, &t) // Unacceptable: Too vague!
```

### Functions and Methods

- Use `camelCase` for unexported.
- Use `PascalCase` for exported.
- Function names must be verb-based and explicit.
- Avoid abbreviations.

**Good:**
```go
func EnqueueHeightmapJob() {}
func ValidateRequestPayload() {}
func EmitScrumBlockerClearEvent() {}
```

---

## File Structure Rules

- One distinct domain responsibility per file.
- Keep dependency boundaries explicit (interfaces layered properly).
- Keep side effects near entry points.

---

## Commenting Rules (Critical)

### Comment Density

- **CRITICAL REQUIREMENT:** Add a meaningful comment (1 or more comments) every 3 logical lines or less in all execution paths.
- Explain intent and constraints, not obvious syntax.
- Prioritize *why* over *what*.
- Every single logical block of operations must be prefaced with a comment explaining the goal of the block.

### Godoc / Docstrings

- **CRITICAL REQUIREMENT:** Every single exported package, function, struct, interface, and variable must have a complete `Godoc` string. 
- The docstring must begin with the name of the exported item.

```go
// ExtractFencedCodeBlocks searches the raw markdown text strictly for 
// triple-backtick fenced regions and parses them into physical blocks.
//
// This function explicitly searches for block-level fences and avoids
// matching inline code by requiring them to start on a new line.
func ExtractFencedCodeBlocks(text string) ([]string, error) {
    // ...
}
```

### Inline Comments

- Comments within function bodies should clarify complex logic, linking related steps together.

```go
// Extract the universal tracking ID from the marker filename
// to establish the rigid routing destination.
filename := filepath.Base(markerPath)
jobID := strings.Replace(filename, "_handoff.md", "", 1)

// Throw a fatal error immediately if the output contract is missing, 
// since Vera physically cannot test a void payload.
if len(jobID) == 0 {
    return fmt.Errorf("empty job ID payload received")
}
```

---

## Error Handling Rules

- Fail fast and explicitly.
- **Never** swallow errors silently using `_ = err` unless accompanied by an explicit multi-line comment explaining exactly why it is safe to ignore.
- Always wrap errors with context (`fmt.Errorf("failed to fetch user: %w", err)`).
- Include enough context in wrapped errors for immediate operator triage.

**Good:**
```go
if _, err := os.Stat(sourcePath); os.IsNotExist(err) {
    return fmt.Errorf("missing source file for pipeline execution at: %s", sourcePath)
}
```

---

## Final Rule

If a future reader must guess intent, the code is wrong.
Baseline compliance is required.
Clarity is the absolute priority.
