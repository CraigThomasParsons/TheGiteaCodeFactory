"""Outside-in tests for skills/slice-pipeline/scripts/pipeline.py.

`codex` and `tmux` are replaced by small fake programs on PATH that record
their arguments and standard input and reply as scripted, so no agent or tmux
session ever starts.

Contract summary:
* `phase` runs one Codex phase in a Git worktree and writes a result file;
  exit 0 only when Codex exits 0 with a valid receipt for that phase.
* `run` performs supervisor ticks until a decision other than `continue` and
  records the outcome in supervisor-status.json next to the state file.
* `start` launches `run` in a detached tmux session named from the state path;
  `status` reports that session and the last supervisor outcome.
* Refusals exit 1 with the reason on stderr.
"""

import fcntl
import hashlib
import json
import os
import shlex
import subprocess
import unittest
from pathlib import Path

from support import HelperTestCase, base_env, run_tool, tool_path, write_executable

FAKE_CODEX = r'''
import json, os, sys
from pathlib import Path
root = Path(os.environ["FAKE_CODEX_DIR"])
index = len(list(root.glob("call-*.json")))
args = sys.argv[1:]
(root / f"call-{index}.json").write_text(json.dumps({"args": args, "stdin": sys.stdin.read()}))
print(json.dumps({"type": "fake-event", "call": index}))
print("fake codex stderr", file=sys.stderr)
for name in (f"response-{index}.json", "response.json"):
    if (root / name).exists():
        Path(args[args.index("-o") + 1]).write_text((root / name).read_text())
        break
code = root / f"exit-{index}"
sys.exit(int(code.read_text()) if code.exists() else 0)
'''

FAKE_TMUX = r'''
import json, os, sys
from pathlib import Path
root = Path(os.environ["FAKE_TMUX_DIR"])
with (root / "calls.jsonl").open("a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")
if sys.argv[1:2] == ["has-session"]:
    sys.exit(0 if (root / "session-exists").exists() else 1)
sys.exit(0)
'''


def receipt(phase="IMPL", **changes):
    value = {"issue_url": "https://gitea.example/o/r/issues/4", "phase": phase, "base_sha": "b" * 40,
             "head_sha": "c" * 40, "changed_files": ["src/a.py"], "scope_statement": "Only issue 4",
             "validation": [{"command": "make test", "exit_code": 0, "evidence_path": "logs/test.txt"}],
             "push_status": "pushed", "pr_url": "https://gitea.example/o/r/pulls/9",
             "discovered_issue_urls": [], "blockers": [], "status": "complete", "next_phase": "SIMPLIFY"}
    value.update(changes)
    return value


class PipelineTestCase(HelperTestCase):
    def setUp(self):
        super().setUp()
        self.bin = self.tmp / "bin"
        self.codex_dir = self.tmp / "codex"
        self.tmux_dir = self.tmp / "tmux"
        self.codex_dir.mkdir()
        self.tmux_dir.mkdir()
        write_executable(self.bin / "codex", FAKE_CODEX)
        write_executable(self.bin / "tmux", FAKE_TMUX)

    def env(self):
        return base_env(self.home, {"PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
                                    "FAKE_CODEX_DIR": str(self.codex_dir), "FAKE_TMUX_DIR": str(self.tmux_dir)})

    def pipeline(self, *args, timeout=60):
        return run_tool("pipeline", list(args), env=self.env(), timeout=timeout)

    def codex_reply(self, value, index=None, exit_code=None):
        name = "response.json" if index is None else f"response-{index}.json"
        (self.codex_dir / name).write_text(value if isinstance(value, str) else json.dumps(value))
        if exit_code is not None:
            (self.codex_dir / f"exit-{index or 0}").write_text(str(exit_code))

    def codex_calls(self):
        calls = sorted(self.codex_dir.glob("call-*.json"), key=lambda p: int(p.stem.split("-")[1]))
        return [json.loads(p.read_text()) for p in calls]

    def tmux_calls(self):
        path = self.tmux_dir / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class PhaseTest(PipelineTestCase):
    def setUp(self):
        super().setUp()
        self.worktree = self.tmp / "worktree"
        self.worktree.mkdir()
        self.git("init", "-q", "-b", "feat/issue-4")
        self.git("remote", "add", "origin", "ssh://git@gitea.example:2222/owner/repo.git")
        self.packet = self.tmp / "packet.md"
        self.packet.write_text("Issue 4: add the widget\nAcceptance: widget renders\n")
        self.result = self.tmp / "results" / "impl.json"

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.worktree), *args], check=True, capture_output=True,
                       env=base_env(self.home, {"GIT_CONFIG_NOSYSTEM": "1"}))

    def phase(self, phase="IMPL"):
        return self.pipeline("phase", "--phase", phase, "--worktree", self.worktree, "--prompt", self.packet,
                             "--result", self.result)

    def read_result(self):
        return json.loads(self.result.read_text())

    def test_successful_phase(self):
        self.codex_reply(receipt())
        result = self.phase()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        attempt = self.result.with_suffix(".attempt")
        self.assertEqual(self.read_result(), {"exit_code": 0, "attempt_dir": str(attempt), "receipt": receipt()})
        [call] = self.codex_calls()
        self.assertEqual(call["args"], ["exec", "--skip-git-repo-check", "-C", str(self.worktree), "--json",
                                        "--output-schema", str(attempt / "schema.json"),
                                        "-o", str(attempt / "response.json"), "-"])
        prompt = (attempt / "prompt.txt").read_text()
        self.assertEqual(call["stdin"], prompt)
        self.assertIn("Execute exactly the IMPL phase.", prompt)
        self.assertIn(str(tool_path("pipeline").parents[2] / "tdd" / "SKILL.md"), prompt)
        self.assertTrue(prompt.endswith("Issue packet:\n" + self.packet.read_text() + "\n"))
        self.assertIn('"call": 0', (attempt / "events.jsonl").read_text())
        self.assertEqual((attempt / "stderr.log").read_text(), "fake codex stderr\n")
        schema = json.loads((attempt / "schema.json").read_text())
        self.assertEqual(set(schema["required"]), set(receipt()))
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(self.result.stat().st_mode & 0o777, 0o600)

    def test_each_phase_names_its_skill(self):
        skills = {"IMPL": "tdd", "SIMPLIFY": "simplify", "ARCHITECTURE": "improve-codebase-architecture",
                  "REVIEW": "code-review", "PR": "tmux-pipeline"}
        for phase, skill in skills.items():
            with self.subTest(phase=phase):
                self.result = self.tmp / "results" / f"{phase}.json"
                self.codex_reply(receipt(phase))
                result = self.phase(phase)
                self.assertEqual(result.returncode, 0, result.stderr)
                prompt = (self.result.with_suffix(".attempt") / "prompt.txt").read_text()
                self.assertIn(f"Execute exactly the {phase} phase.", prompt)
                self.assertIn(f"/{skill}/SKILL.md", prompt)

    def test_receipt_for_another_phase_is_rejected(self):
        self.codex_reply(receipt("REVIEW"))
        result = self.phase("IMPL")
        self.assertEqual(result.returncode, 1)
        written = self.read_result()
        self.assertIsNone(written["receipt"])
        self.assertEqual(written["error"], "Receipt phase does not match the dispatched phase")

    def test_codex_failure(self):
        self.codex_reply(receipt(), index=0, exit_code=3)
        result = self.phase()
        self.assertEqual(result.returncode, 1)
        written = self.read_result()
        self.assertEqual((written["exit_code"], written["receipt"]), (3, None))
        self.assertNotIn("error", written)

    def test_invalid_or_missing_receipt(self):
        cases = {"missing field": {k: v for k, v in receipt().items() if k != "pr_url"},
                 "extra field": dict(receipt(), extra="x"),
                 "bad status": receipt(status="done"),
                 "bool exit code": receipt(validation=[{"command": "x", "exit_code": True, "evidence_path": "p"}]),
                 "string list": receipt(changed_files="a.py"),
                 "not json": "{nope"}
        for label, value in cases.items():
            with self.subTest(case=label):
                self.result = self.tmp / "results" / f"{label.replace(' ', '-')}.json"
                self.codex_reply(value)
                result = self.phase()
                self.assertEqual(result.returncode, 1)
                written = self.read_result()
                self.assertEqual(written["exit_code"], 0)
                self.assertIsNone(written["receipt"])
                self.assertTrue(written["error"].startswith("Invalid or missing response: "), written["error"])
        (self.codex_dir / "response.json").unlink()
        self.result = self.tmp / "results" / "no-response.json"
        self.assertEqual(self.phase().returncode, 1)
        self.assertTrue(self.read_result()["error"].startswith("Invalid or missing response: "))

    def test_existing_result_is_never_overwritten(self):
        self.result.parent.mkdir(parents=True)
        self.result.write_text("earlier")
        result = self.phase()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "Result exists; use a new attempt path after reconciling previous evidence\n")
        self.assertEqual(self.result.read_text(), "earlier")
        self.assertEqual(self.codex_calls(), [])

    def test_remote_must_name_owner_and_repository(self):
        for origin, message in [("/srv/git/repo.git", "Remote must identify a hosted owner/repository"),
                                ("https://gitea.example/group/sub/repo.git", "Remote must identify exactly owner/repository"),
                                ("https://gitea.example/repo", "Remote must identify exactly owner/repository")]:
            with self.subTest(origin=origin):
                self.git("remote", "set-url", "origin", origin)
                result = self.phase()
                self.assertEqual((result.returncode, result.stderr), (1, message + "\n"))
        self.assertEqual(self.codex_calls(), [])

    def test_accepted_remote_forms(self):
        for index, origin in enumerate(["git@gitea.example:owner/repo.git", "https://gitea.example/owner/repo",
                                        "ssh://git@gitea.example:2222/owner/repo/"]):
            with self.subTest(origin=origin):
                self.git("remote", "set-url", "origin", origin)
                self.result = self.tmp / "results" / f"remote-{index}.json"
                self.codex_reply(receipt())
                self.assertEqual(self.phase().returncode, 0)

    def test_worktree_without_origin_fails(self):
        self.git("remote", "remove", "origin")
        result = self.phase()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.codex_calls(), [])

    def test_branch_lock_is_shared_across_worktrees(self):
        key = hashlib.sha256(b"owner/repo:feat/issue-4").hexdigest()
        lock_dir = self.home / ".local" / "state" / "gitea-night" / "branches"
        lock_dir.mkdir(parents=True)
        with (lock_dir / f"{key}.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = self.phase()
        self.assertEqual((result.returncode, result.stderr), (1, "Another worker owns this repository branch\n"))

    def test_worktree_lock(self):
        key = hashlib.sha256(str(self.worktree).encode()).hexdigest()
        lock_dir = self.home / ".local" / "state" / "slice-pipeline" / "worktree-locks"
        lock_dir.mkdir(parents=True)
        with (lock_dir / key).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = self.phase()
        self.assertEqual((result.returncode, result.stderr), (1, "Another phase owns this worktree\n"))

    def test_unknown_phase_is_a_usage_error(self):
        result = self.phase("DEPLOY")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.codex_calls(), [])


class SupervisorTest(PipelineTestCase):
    def setUp(self):
        super().setUp()
        self.workspace = self.tmp / "workspace"
        self.workspace.mkdir()
        self.state = self.tmp / "state" / "pipeline.json"
        self.status_file = self.state.parent / "supervisor-status.json"

    def session(self):
        return "slice-" + hashlib.sha256(str(self.state.resolve()).encode()).hexdigest()[:12]

    def test_run_one_tick_until_review(self):
        self.codex_reply({"decision": "awaiting_review", "reason": "PR 9 is ready"})
        result = self.pipeline("run", "--state", self.state, "--workspace", self.workspace)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        status = json.loads(self.status_file.read_text())
        self.assertEqual({k: status[k] for k in ("status", "reason")}, {"status": "awaiting_review", "reason": "PR 9 is ready"})
        attempt = Path(status["attempt"])
        self.assertEqual(attempt.parent, self.state.parent / "ticks")
        state = json.loads(self.state.read_text())
        self.assertEqual(state["workspace"], str(self.workspace))
        self.assertEqual((state["status"], state["queue"], state["tick"]), ("running", [], 0))
        [call] = self.codex_calls()
        self.assertEqual(call["args"][:4], ["exec", "--skip-git-repo-check", "-C", str(self.workspace)])
        self.assertIn("performing exactly ONE tick for state " + str(self.state), call["stdin"])
        schema = json.loads((attempt / "schema.json").read_text())
        self.assertEqual(schema["properties"]["decision"]["enum"], ["continue", "awaiting_review", "blocked", "complete"])

    def test_run_continues_until_a_stopping_decision(self):
        self.codex_reply({"decision": "continue", "reason": "dispatched"}, index=0)
        self.codex_reply({"decision": "complete", "reason": "all done"}, index=1)
        result = self.pipeline("run", "--state", self.state, "--workspace", self.workspace, "--interval", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.codex_calls()), 2)
        self.assertEqual(json.loads(self.status_file.read_text())["status"], "complete")

    def test_existing_state_keeps_its_workspace(self):
        other = self.tmp / "other"
        other.mkdir()
        self.write_json("state/pipeline.json", {"workspace": str(other), "queue": [{"issue": 1}], "status": "running"})
        self.codex_reply({"decision": "blocked", "reason": "needs a human"})
        result = self.pipeline("run", "--state", self.state, "--workspace", self.workspace)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.codex_calls()[0]["args"][3], str(other))
        self.assertEqual(json.loads(self.state.read_text())["queue"], [{"issue": 1}])
        self.assertEqual(json.loads(self.status_file.read_text())["status"], "blocked")

    def test_failed_tick_is_recorded_as_blocked(self):
        # The run itself exits 0; the outcome is in supervisor-status.json.
        for label, reply, code in [("exit", {"decision": "continue", "reason": "x"}, 1),
                                   ("invalid", {"decision": "maybe", "reason": "x"}, None)]:
            with self.subTest(case=label):
                for path in self.codex_dir.iterdir():
                    path.unlink()
                self.codex_reply(reply, index=0, exit_code=code)
                result = self.pipeline("run", "--state", self.state, "--workspace", self.workspace)
                self.assertEqual(result.returncode, 0, result.stderr)
                status = json.loads(self.status_file.read_text())
                self.assertEqual((status["status"], status["reason"], status["live_pid"]),
                                 ("blocked", "Supervisor failed; inspect private attempt logs", None))

    def test_run_refusals(self):
        first = self.pipeline("run", "--state", self.state)
        self.assertEqual((first.returncode, first.stderr), (1, "Workspace required for first start\n"))
        zero = self.pipeline("run", "--state", self.state, "--workspace", self.workspace, "--interval", "0")
        self.assertEqual((zero.returncode, zero.stderr), (1, "Interval must be positive\n"))
        self.write_json("state/pipeline.json", {"workspace": str(self.tmp / "gone"), "queue": []})
        gone = self.pipeline("run", "--state", self.state)
        self.assertEqual((gone.returncode, gone.stderr), (1, "Workspace missing\n"))
        self.write_json("state/pipeline.json", {"workspace": str(self.workspace), "queue": {}})
        bad = self.pipeline("run", "--state", self.state)
        self.assertEqual((bad.returncode, bad.stderr), (1, "Invalid queue\n"))
        self.assertEqual(self.codex_calls(), [])

    def test_run_refuses_after_an_unreconciled_timeout(self):
        self.write_json("state/supervisor-status.json", {"status": "blocked", "live_pid": 4242})
        result = self.pipeline("run", "--state", self.state, "--workspace", self.workspace)
        self.assertEqual(result.returncode, 1)
        self.assertIn("unreconciled process", result.stderr)
        self.assertEqual(self.codex_calls(), [])

    def test_run_lock(self):
        self.state.parent.mkdir(parents=True)
        with self.state.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = self.pipeline("run", "--state", self.state, "--workspace", self.workspace)
        self.assertEqual((result.returncode, result.stderr), (1, "Supervisor already owns this state\n"))

    def test_status(self):
        result = self.pipeline("status", "--state", self.state)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"session": self.session(), "alive": False,
                                                     "state": str(self.state), "last": None})
        self.assertEqual(self.tmux_calls(), [["has-session", "-t", self.session()]])
        (self.tmux_dir / "session-exists").write_text("")
        self.write_json("state/supervisor-status.json", {"status": "awaiting_review", "reason": "r", "attempt": "a"})
        report = json.loads(self.pipeline("status", "--state", self.state).stdout)
        self.assertIs(report["alive"], True)
        self.assertEqual(report["last"], {"status": "awaiting_review", "reason": "r", "attempt": "a"})

    def test_start_launches_run_in_tmux(self):
        result = self.pipeline("start", "--state", self.state, "--workspace", self.workspace, "--interval", "30")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"Started {self.session()}; inspect status and first tick before claiming healthy delivery\n")
        has, new = self.tmux_calls()
        self.assertEqual(has, ["has-session", "-t", self.session()])
        self.assertEqual(new[:4], ["new-session", "-d", "-s", self.session()])
        argv = shlex.split(new[4])
        self.assertEqual(Path(argv[1]), tool_path("pipeline"))
        self.assertEqual(argv[2:], ["run", "--state", str(self.state), "--interval", "30", "--workspace", str(self.workspace)])
        self.assertEqual(self.codex_calls(), [])

    def test_start_with_existing_state_needs_no_workspace(self):
        self.write_json("state/pipeline.json", {"workspace": str(self.workspace), "queue": []})
        result = self.pipeline("start", "--state", self.state)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(shlex.split(self.tmux_calls()[1][4])[2:], ["run", "--state", str(self.state), "--interval", "60"])

    def test_start_refusals_and_existing_session(self):
        result = self.pipeline("start", "--state", self.state)
        self.assertEqual((result.returncode, result.stderr), (1, "Pass --workspace for first start\n"))
        (self.tmux_dir / "session-exists").write_text("")
        again = self.pipeline("start", "--state", self.state, "--workspace", self.workspace)
        self.assertEqual(again.returncode, 0)
        self.assertEqual(again.stdout, f"Supervisor session already exists: {self.session()}\n")
        self.assertEqual([c[0] for c in self.tmux_calls()], ["has-session"])
        zero = self.pipeline("start", "--state", self.state, "--workspace", self.workspace, "--interval", "0")
        self.assertEqual((zero.returncode, zero.stderr), (1, "Interval must be positive\n"))

    def test_subcommand_required(self):
        self.assertNotEqual(self.pipeline().returncode, 0)


if __name__ == "__main__":
    unittest.main()
