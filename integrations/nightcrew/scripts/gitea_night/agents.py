"""Bounded Claude-first agent adapters with one Codex fallback."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from .runtime import inherited_locks


class ProviderFailure(RuntimeError):
    """A confirmed provider process or structured-output failure."""


def _clean_environment():
    """Keep provider authentication while withholding workflow service tokens."""
    environment = os.environ.copy()
    for name in ("GITEA_TOKEN", "NIGHT_CREW_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        environment.pop(name, None)
    return environment


def _run(command, cwd, timeout):
    """Run one provider process and classify all non-results as provider failure."""
    try:
        completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
            env=_clean_environment(), pass_fds=inherited_locks())
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProviderFailure(str(error)) from error
    if completed.returncode != 0:
        raise ProviderFailure((completed.stderr or completed.stdout)[-4000:])
    return completed.stdout


def claude(prompt: str, cwd: str, schema: dict, writable: bool):
    """Invoke personal Claude with an explicit tool and permission boundary."""
    tools = "Read,Grep,Glob,Bash" if not writable else "Read,Grep,Glob,Edit,Write"
    mode = "plan" if not writable else "acceptEdits"
    output = _run(["claude", "-p", prompt, "--output-format", "json", "--json-schema",
        json.dumps(schema), "--tools", tools, "--permission-mode", mode,
        "--no-session-persistence"], cwd, 3600)
    envelope = json.loads(output)
    result = envelope.get("structured_output")
    if not isinstance(result, dict):
        raise ProviderFailure("Claude returned no structured_output")
    return result


def codex(prompt: str, cwd: str, schema: dict, writable: bool):
    """Invoke Codex once with the same task after confirmed Claude failure."""
    sandbox = "workspace-write" if writable else "read-only"
    with tempfile.TemporaryDirectory(prefix="gitea-night-codex-") as directory:
        schema_path = Path(directory) / "schema.json"
        result_path = Path(directory) / "result.json"
        schema_path.write_text(json.dumps(schema))
        _run(["codex", "exec", "--ephemeral", "--sandbox", sandbox, "--cd", cwd,
            "--output-schema", str(schema_path), "--output-last-message", str(result_path), prompt], cwd, 3600)
        try:
            result = json.loads(result_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise ProviderFailure("Codex returned no structured result") from error
    if not isinstance(result, dict):
        raise ProviderFailure("Codex result was not an object")
    return result


def run(prompt: str, cwd: str, schema: dict, writable: bool = False):
    """Use personal Claude first and preserve the task for exactly one Codex fallback."""
    try:
        return claude(prompt, cwd, schema, writable), "claude", None
    except ProviderFailure as claude_error:
        result = codex(prompt, cwd, schema, writable)
        return result, "codex", str(claude_error)
