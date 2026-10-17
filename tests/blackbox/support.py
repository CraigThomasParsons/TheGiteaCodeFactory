"""Shared helpers for the outside-in helper tests.

Every test here drives a helper only through its command line: arguments,
input files, environment variables and standard input go in; standard output,
standard error, the exit code and written files come out. Nothing imports a
helper's code, so the same tests run against the original Python/JavaScript and
against the files generated from Haxe source (docs/adr/0001).

Choosing the implementation under test:

* ``GCF_TOOL_ROOT``: a directory laid out like this repository (default: the
  repository itself). Each helper is found at its usual relative path.
* ``GCF_TOOL_<NAME>``: overrides one helper's path, for example
  ``GCF_TOOL_PARITY=/tmp/port/parity.py``. Names are the keys of ``TOOLS``
  in upper case.

A ``.py`` helper runs with the current Python interpreter and a ``.js`` helper
with ``node``.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

REPO = Path(__file__).resolve().parents[2]

TOOLS = {
    "classify": "skills/supervise-agent-pipeline/scripts/classify_execution.py",
    "coach": "scripts/coach.py",
    "dispatcher_gitea": "skills/dispatcher/scripts/gitea.py",
    "gitea_merge": "skills/pr-review-resolve-loop/scripts/gitea_merge.py",
    "install_skills": "scripts/install-skills.py",
    "parity": "scripts/parity.py",
    "pipeline": "skills/slice-pipeline/scripts/pipeline.py",
    "retalk_bridge": "skills/retalk-bridge/scripts/retalk_bridge.py",
    "reviewer": "scripts/reviewer/ai_pr_reviewer.js",
}


def tool_path(name: str) -> Path:
    """Return the path of the implementation under test for helper ``name``."""
    override = os.environ.get("GCF_TOOL_" + name.upper())
    if override:
        return Path(override).resolve()
    root = Path(os.environ.get("GCF_TOOL_ROOT", str(REPO))).resolve()
    return root / TOOLS[name]


def base_env(home: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    """A minimal environment: no inherited tokens, API keys or Gitea settings."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TMPDIR": tempfile.gettempdir(),
    }
    if extra:
        env.update(extra)
    return env


def run_tool(name: str, args: list[str], *, env: dict[str, str], stdin: str | None = None,
             cwd: Path | None = None, timeout: float = 60) -> subprocess.CompletedProcess:
    """Run helper ``name`` with ``args`` and return the completed process."""
    path = tool_path(name)
    if path.suffix == ".js":
        command = [shutil.which("node") or "node", str(path)]
    else:
        command = [sys.executable, str(path)]
    return subprocess.run(command + [str(a) for a in args], env=env, input=stdin, cwd=cwd,
                          capture_output=True, text=True, timeout=timeout)


def last_json_line(text: str):
    """Parse the last non-empty line of ``text`` as JSON."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise AssertionError("expected JSON output, got nothing")
    return json.loads(lines[-1])


class HelperTestCase(unittest.TestCase):
    """Gives each test a private temporary directory and HOME."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.addCleanup(self._tmp.cleanup)

    def write_json(self, relative: str, value) -> Path:
        path = self.tmp / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return path


class Request:
    """One request received by ``FakeServer``."""

    def __init__(self, method, path, query, headers, body):
        self.method = method
        self.path = path
        self.query = query
        self.headers = headers
        self.body = body

    def json(self):
        return json.loads(self.body) if self.body else None


class FakeServer:
    """A local HTTP server whose responses come from a Python callable.

    ``handler(request)`` returns ``(status, body)`` or ``(status, body, headers)``.
    A body that is not bytes or str is sent as JSON. Every request is recorded
    in ``requests``.
    """

    def __init__(self, handler):
        self.handler = handler
        self.requests: list[Request] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _handle(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode() if length else ""
                parts = urlsplit(self.path)
                request = Request(self.command, parts.path, parse_qs(parts.query),
                                  {k.lower(): v for k, v in self.headers.items()}, body)
                outer.requests.append(request)
                result = outer.handler(request)
                status, payload = result[0], result[1]
                headers = result[2] if len(result) > 2 else {}
                if isinstance(payload, bytes):
                    data = payload
                elif isinstance(payload, str):
                    data = payload.encode()
                else:
                    data = json.dumps(payload).encode()
                    headers = {"Content-Type": "application/json", **headers}
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = _handle

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05},
                                       daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def matching(self, method: str, path_suffix: str = "") -> list[Request]:
        return [r for r in self.requests if r.method == method and r.path.endswith(path_suffix)]


def write_executable(path: Path, source: str) -> Path:
    """Write a small Python program as an executable script (used for fake CLIs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!{sys.executable}\n" + source)
    path.chmod(0o755)
    return path


deepcopy = copy.deepcopy
