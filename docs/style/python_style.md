# Python Coding Style and Commenting Conventions (Project Standard)

This document defines the required Python coding style for
AgileMedievalPeasantBoard automation, NAS deployment scripts, agent pipeline
tools, and related maintenance utilities.

The primary goal is clarity, explicitness, and long-term maintainability.

---

## Core Philosophy

- Code must be readable first and clever second.
- Explicit behavior is preferred over compact tricks.
- Descriptive names are required for variables, functions, and files.
- Future readers should understand intent without external context.
- Runtime paths should be boring, predictable, and easy to debug.
- NAS automation must be auditable before it touches the server.

---

## Standards Baseline

This project follows these Python conventions:

- Modern Python 3 semantics with type hints where possible.
- Strict enforcement of explicit variable scopes and intent.
- Consistent formatting with 4 spaces for indentation (PEP 8 baseline).
- Pylance/Pyright-compatible type annotations for functions, collections, and JSON data.

Where standard PEP 8 is silent or flexible, this document defines project-specific rules.

---

## Static Analysis

- Resolve Pylance/Pyright warnings before handing off Python changes.
- Do not index or mutate a union type until the shape has been narrowed with `isinstance`,
  overloads, helper functions, or explicit validation.
- Use `typing.NoReturn` for helpers that always exit or raise so callers do not appear to
  fall through to `None`.
- Use `dict[str, Any]`, `list[Any]`, `TypedDict`, dataclasses, or overloads to describe JSON
  shapes instead of broad unvalidated `dict | list` returns.
- Avoid `# type: ignore` unless the reason is documented and the alternative would make the
  code less clear.

Recommended local checks:

```bash
pytest scripts/tools/tests
python3 -m py_compile scripts/tools/**/*.py
```

When `pyright` or `basedpyright` is installed, run it on changed Python files or the relevant
script directory before handoff.

---

## Naming Conventions (Locked)

### Variables and Properties

- Use `snake_case`.
- Use descriptive multi-word names.
- Never use single-letter variable names except conventional short values such as `i` in
  simple loops.

Good:

```python
decoded_request_payload = json.loads(raw_request_body)
deployment_root_path = resolve_deployment_root_path(factory_root)
```

### Constants

- Use `UPPER_SNAKE_CASE` for true constants and module-level immutable values.

Good:

```python
DEFAULT_NAS_HOST = "192.0.2.10"
```

### Functions

- Use `snake_case`.
- Function names must be verb-based and explicit.
- Avoid abbreviations and generic names.

Good:

```python
def verify_runner_service_status(): pass
def build_remote_status_command(): pass
def emit_deployment_diagnostic_report(): pass
```

---

## File Structure Rules

- One responsibility per file.
- Avoid mixing transport, domain logic, and formatting in the same function.
- Keep I/O boundaries explicit.
- Keep side effects near entry points.
- For NAS SSH work, create or update a script in `scripts/tools/`, commit it, then run it.

---

## NAS SSH Automation Rule

Every SSH command intended to run on the NAS must live in a Python script under
`scripts/tools/` and be committed before execution.

Do not use bare terminal SSH commands or ad hoc SSH heredocs for NAS operations.
This preserves a reviewable audit trail for deployment changes, server
inspection, and incident recovery.

Python scripts may invoke SSH through `subprocess`, but the remote command must
be named, documented, and narrow enough for a future reader to understand why it
exists.

---

## Commenting Rules (Critical)

### Comment Density

- **CRITICAL REQUIREMENT:** Add a meaningful comment every 3 logical lines or less in
  all execution paths.
- Explain intent and constraints, not obvious syntax.
- Prioritize *why* over *what*.

This requirement is about preserving intent, not padding files. Good comments explain
deployment constraints, NAS safety rules, security assumptions, retry behavior, and failure
handling. Do not add filler comments that merely repeat the syntax, and prefer clearer names
or smaller functions when the code itself is hard to follow.

### Sphinx Docstrings

- Use docstrings for all modules, classes, and functions to document purpose and constraints.
- Use Sphinx-style `:param name:` entries for every function parameter.
- Leave out `:return:` only when a function returns `None`.
- Include `:return:` for every non-`None` return value.
- Use `typing.NoReturn` for helpers that always exit or raise, then document that with
  `:return:`.
- Keep one empty line between the description and tags.
- Keep one empty line between `:param` tags and the `:return:` tag.

```python
def extract_fenced_code_blocks(markdown_text: str) -> list[str]:
    """
    Extract triple-backtick fenced code blocks from markdown text.

    This function searches for block-level fences and avoids matching inline
    code by requiring fences to start on a new line.

    :param markdown_text: Markdown content that may contain fenced code blocks.

    :return: Extracted block contents in document order.
    """
    pass
```

For process-exit helpers, make the type checker aware that the function cannot return:

```python
from typing import NoReturn


def die(message: str) -> NoReturn:
    """
    Print an error and exit the process.

    :param message: Human-readable failure reason for the operator.

    :return: Never returns because the process exits with a non-zero status.
    """
    print(message)
    raise SystemExit(1)
```

### Inline Comments

Comments should clarify complex logic, linking related steps together.

```python
# Reuse the existing runner service name so repeated diagnostics compare the
# same systemd unit across deploy attempts.
runner_service_name = "act_runner.service"

# Reject empty output early so the diagnostic report cannot claim a successful
# check when SSH returned no data.
if remote_output.strip() == "":
    raise RuntimeError("NAS diagnostic command returned no output")
```

---

## Error Handling Rules

- Fail fast and explicitly.
- Never swallow errors silently or use bare `except:` clauses without re-raising or logging
  appropriately.
- Use guard clauses before deep nesting.
- Include enough context in errors for operator triage.

Good:

```python
if not deployment_root_path.exists():
    raise FileNotFoundError(f"Missing NAS deployment root: {deployment_root_path}")
```

---

## Final Rule

If a future reader must guess intent, the code is wrong.
Baseline compliance is required.
Clarity is the priority.
