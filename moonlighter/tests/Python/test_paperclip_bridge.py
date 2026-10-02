"""Behavioural tests for the Paperclip -> NightCrew process bridge."""
import argparse
import datetime as dt
import http.server
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "tools"))
import paperclip_bridge as bridge  # noqa: E402

REPO = "owner/ExampleGame"
WORKER = "nas-01"
START = dt.datetime(2026, 9, 27, 12, 0, tzinfo=dt.timezone.utc)

LAUNCHER = r'''
import json, os, subprocess, sys, time
from pathlib import Path
job_id, receipt_path, provider, revision, resume = sys.argv[1:6]
home = Path(os.environ["FAKE_HOME"])
with (home / "calls.log").open("a") as log:
    log.write(json.dumps({"job": job_id, "provider": provider, "resume": resume}) + "\n")
plan = json.loads((home / "plan.json").read_text()).get(provider, {})
if plan.get("wait_for"):
    (home / "started").write_text("1")
    while not Path(plan["wait_for"]).exists():
        time.sleep(0.02)
if plan.get("touch"):
    Path(plan["touch"]).write_text("uncommitted work in progress\n")
if plan.get("commit"):
    subprocess.run(["git", "add", "-A"], check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.test", "commit", "-qm", "work"],
        check=True)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        check=True).stdout.strip()
receipt = plan.get("receipt")
if receipt is not None:
    receipt = {"job_id": job_id, "revision": revision, "attempt": int(os.environ["NIGHTCREW_BRIDGE_ATTEMPT"]),
        "attempt_nonce": os.environ["NIGHTCREW_BRIDGE_ATTEMPT_NONCE"], "repo": os.environ["NIGHTCREW_BRIDGE_REPO"],
        "worktree": os.getcwd(), **receipt}
    Path(receipt_path).write_text(json.dumps(receipt))
sys.exit(plan.get("exit", 0))
'''
PASSED = {"passed": True, "commands": [{"command": "pytest", "exit_code": 0}]}


class Clock:
    """A controllable clock so cooldown expiry is deterministic."""

    def __init__(self):
        self.moment = START

    def __call__(self):
        return self.moment


class FakeApi:
    """In-memory NightCrew honouring the real claim/held/status contract."""

    def __init__(self, served=(REPO,), worker_id=WORKER):
        self.identity = {"worker_id": worker_id, "served_repos": list(served)}
        self.queue = []
        self.jobs = {}
        self.claims = 0
        self.transitions = []
        self.requests = []
        self.lose_next_claim_response = False

    def add(self, job_id, repo=REPO, contested=False, kind="issue"):
        self.queue.append({"id": job_id, "repo": repo, "kind": kind, "reference": str(job_id),
            "status": "queued", "contested": contested, "claim_token": None})

    def me(self):
        self.requests.append("GET /worker/me")
        return self.identity

    def held(self):
        self.requests.append("GET /worker/jobs")
        return [dict(job) for job in self.jobs.values()
            if job["worker_id"] == WORKER and job["status"] in ("claimed", "running")]

    def claim(self):
        self.requests.append("POST /claim-next")
        self.claims += 1
        if not self.queue:
            return None
        job = self.queue.pop(0)
        job.update(status="claimed", worker_id=WORKER)
        self.jobs[job["id"]] = job
        if self.lose_next_claim_response:
            # The row committed server-side but the response never arrived.
            self.lose_next_claim_response = False
            raise urllib.error.URLError("connection reset")
        return dict(job)

    def status(self, job, status, receipt):
        self.requests.append(f"PATCH /jobs/{job['id']}/status")
        self.transitions.append((job["id"], status, receipt))
        self.jobs[job["id"]]["status"] = status
        return {"data": self.jobs[job["id"]]}


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A git worktree, a fake launcher, a config and a fake coordinator."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    git = ["git", "-C", str(worktree), "-c", "user.name=t", "-c", "user.email=t@example.test"]
    subprocess.run(git[:3] + ["init", "-q"], check=True)
    subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "base"], check=True)
    (tmp_path / "launcher.py").write_text(LAUNCHER)
    (tmp_path / "plan.json").write_text("{}")
    monkeypatch.setenv("FAKE_HOME", str(tmp_path))
    monkeypatch.setenv("NIGHTCREW_TOKEN", "super-secret-token")
    argv = [sys.executable, str(tmp_path / "launcher.py"), "{job_id}", "{receipt_path}", "{provider}",
        "{revision}", "{resume}"]
    # Dispatch and the audited done path are opted into explicitly; tests of the
    # safe defaults remove these keys.
    config = {"api_base": "http://127.0.0.1:9/api", "worker_id": WORKER, "token_env": "NIGHTCREW_TOKEN",
        "state_dir": str(tmp_path / "state"), "timeout_seconds": 30, "dispatch_enabled": True,
        "providers": {"claude": {"cooldown_seconds": 600}, "codex": {"cooldown_seconds": 600}},
        "repositories": {REPO: {"worktree": str(worktree), "providers": ["claude", "codex"], "done_supported": True,
            "launch": {"claude": argv, "codex": argv}}}}
    return World(tmp_path, worktree, config, git)


class World:
    """Test helpers bound to one temporary installation."""

    def __init__(self, home, worktree, config, git):
        self.home = home
        self.worktree = worktree
        self.config = config
        self.git = git
        self.api = FakeApi()
        self.clock = Clock()
        self.alive = lambda pid: False
        self.group_alive = bridge.group_alive

    def plan(self, **providers):
        (self.home / "plan.json").write_text(json.dumps(providers))

    def run(self, command="tick", **options):
        path = self.home / "config.json"
        path.write_text(json.dumps(self.config))
        arguments = argparse.Namespace(command=command, config=str(path), job=options.get("job"),
            to=options.get("to"), evidence=options.get("evidence"), note="", observe=options.get("observe", False))
        return bridge.run(arguments, api=self.api, now=self.clock, alive=self.alive, group_alive=self.group_alive)

    def statuses(self):
        return [status for _, status, _ in self.api.transitions]

    def calls(self):
        log = self.home / "calls.log"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]

    def ledger(self):
        return json.loads((self.home / "state" / "ledger.json").read_text())

    def head(self):
        return subprocess.run(self.git[:3] + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def done_receipt(phase="done", passed=True):
    return {"exit": 0, "receipt": {"phase": phase, "validation": {**PASSED, "passed": passed}}}


def process_gone(pid):
    """True once a pid no longer exists or is only an unreaped zombie."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return True
    return stat[stat.rfind(")") + 2] in "ZX"


class Recorder(http.server.BaseHTTPRequestHandler):
    """Canned-response HTTP server that records every request it receives."""

    def answer(self):
        self.server.seen.append({"method": self.command, "path": self.path,
            "authorization": self.headers.get("Authorization")})
        status, headers, body = self.server.routes.get((self.command, self.path), (404, {}, {"message": "nope"}))
        data = b""
        if body is not None:
            data = json.dumps(body).encode()
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = answer

    def log_message(self, *arguments):
        pass


@pytest.fixture
def server():
    """Start throwaway local HTTP servers with canned routes."""
    started = []

    def start(routes):
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Recorder)
        httpd.routes = routes
        httpd.seen = []
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        started.append(httpd)
        return httpd

    yield start
    for httpd in started:
        httpd.shutdown()
        httpd.server_close()


def base(httpd):
    return f"http://127.0.0.1:{httpd.server_address[1]}/api"


QUOTA = {"exit": 75, "receipt": {"status": "provider_unavailable", "phase": "implement",
    "retry_at": "2026-09-27T13:00:00+00:00"}}


# -- overlapping ticks -------------------------------------------------------

def test_overlapping_tick_is_busy_while_launcher_runs(world):
    world.api.add(1)
    release = world.home / "release"
    world.plan(claude={**done_receipt(), "wait_for": str(release)})
    outcome = {}
    first = threading.Thread(target=lambda: outcome.setdefault("first", world.run()))
    first.start()
    for _ in range(250):
        if (world.home / "started").exists():
            break
        time.sleep(0.02)

    second = world.run()

    release.write_text("go")
    first.join(timeout=20)
    assert second == (0, {"status": "busy", "worker_id": WORKER})
    assert world.api.claims == 1
    assert outcome["first"][1]["status"] == "done"
    assert len(world.calls()) == 1


def test_orphaned_descendant_keeps_the_inherited_lock(world):
    state = world.home / "state"
    state.mkdir()
    descriptor = bridge.acquire_lock(state / "bridge.lock")
    orphan = subprocess.Popen(["sleep", "30"], pass_fds=(descriptor,))
    os.close(descriptor)  # the parent tick "died"; only its descendant holds the lock now
    try:
        assert world.run()[1]["status"] == "busy"
    finally:
        orphan.kill()
        orphan.wait()
    assert world.run()[1]["status"] == "idle"


def test_timeout_kills_descendants_that_ignore_sigterm_before_returning(world):
    world.api.add(91)
    world.config.update(timeout_seconds=2, terminate_grace_seconds=1)
    child_pid = world.home / "child.pid"
    (world.home / "stubborn.py").write_text(
        "import os, signal, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "open(sys.argv[1], 'w').write(str(os.getpid()))\n"
        "time.sleep(120)\n")
    (world.home / "spawner.py").write_text(
        "import os, subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, sys.argv[1], sys.argv[2]])\n"
        "while not os.path.exists(sys.argv[2]):\n"
        "    time.sleep(0.02)\n"
        "time.sleep(120)\n")
    world.config["repositories"][REPO]["launch"]["claude"] = [sys.executable, str(world.home / "spawner.py"),
        str(world.home / "stubborn.py"), str(child_pid)]

    code, result = world.run()

    assert (code, result["reason"]) == (3, "launcher_timeout")
    assert process_gone(int(child_pid.read_text()))


def test_unproven_group_cleanup_halts_instead_of_releasing_ownership(world):
    world.api.add(92)
    world.config.update(timeout_seconds=1, terminate_grace_seconds=0.2)
    world.config["repositories"][REPO]["launch"]["claude"] = [sys.executable, "-c", "import time; time.sleep(120)"]
    world.group_alive = lambda pgid: True

    code, result = world.run()

    assert (code, result["status"], result["reason"]) == (3, "halted", "launcher_cleanup_unproven")
    assert world.ledger()["jobs"]["92"]["state"] == "blocked"
    assert world.run()[1]["status"] == "halted"
    assert world.api.claims == 1


def test_launcher_exit_with_surviving_descendants_is_not_classified(world):
    world.api.add(93)
    world.config["descendant_grace_seconds"] = 0.2
    world.plan(claude=done_receipt())
    world.group_alive = lambda pgid: True

    code, result = world.run()

    assert (code, result["reason"]) == (3, "launcher_descendants_alive")
    assert "done" not in world.statuses()


# -- restart, lost responses and ambiguity ------------------------------------

def test_lost_claim_response_is_adopted_not_reclaimed(world):
    world.api.add(7)
    world.api.add(8)
    world.api.lose_next_claim_response = True
    world.plan(claude=done_receipt())
    with pytest.raises(urllib.error.URLError):
        world.run()
    assert world.ledger()["intent"] is not None

    code, result = world.run()

    assert (code, result["status"], result["job_id"]) == (0, "done", 7)
    assert world.api.claims == 1
    assert [call["job"] for call in world.calls()] == ["7"]
    assert world.ledger()["jobs"]["7"]["source"] == "reconciled_lost_claim_response"


def test_unknown_held_job_without_intent_halts_before_claiming(world):
    world.api.jobs[3] = {"id": 3, "repo": REPO, "kind": "issue", "status": "claimed", "worker_id": WORKER}
    world.api.add(4)

    code, result = world.run()

    assert (code, result["status"], result["reason"]) == (3, "halted", "unknown_held_job")
    assert world.api.claims == 0
    assert world.run()[1]["status"] == "halted"


def test_restart_after_unexpected_death_halts_without_relaunch(world):
    world.api.add(5)
    world.plan(claude=QUOTA)
    world.run()
    ledger = world.ledger()
    ledger["jobs"]["5"].update(state="running", pid=999999)
    Path(ledger["jobs"]["5"]["receipt_path"]).unlink()
    (world.home / "state" / "ledger.json").write_text(json.dumps(ledger))
    calls = len(world.calls())

    code, result = world.run()

    assert (code, result["status"], result["reason"]) == (3, "halted", "unexpected_process_death")
    assert len(world.calls()) == calls
    assert world.api.claims == 1


def test_restart_with_proven_receipt_finishes_without_relaunch(world):
    world.api.add(6)
    world.plan(claude=done_receipt())
    world.run()
    ledger = world.ledger()
    ledger["jobs"]["6"].update(state="running")
    (world.home / "state" / "ledger.json").write_text(json.dumps(ledger))
    world.api.jobs[6]["status"] = "running"
    world.api.transitions.clear()

    world.run()

    assert [status for _, status, _ in world.api.transitions] == ["done"]
    assert len(world.calls()) == 1


def test_restart_with_live_launcher_group_halts_even_with_receipt(world):
    world.api.add(10)
    world.plan(claude=done_receipt())
    world.run()
    ledger = world.ledger()
    ledger["jobs"]["10"].update(state="running", pid=4242)
    (world.home / "state" / "ledger.json").write_text(json.dumps(ledger))
    world.api.jobs[10]["status"] = "running"
    world.api.transitions.clear()
    world.alive = lambda pid: True

    code, result = world.run()

    assert (code, result["reason"]) == (3, "launcher_still_alive")
    assert world.api.transitions == []


def test_claim_lost_in_nightcrew_is_never_acted_on_again(world):
    world.api.add(9)
    world.plan(claude=QUOTA)
    world.run()
    world.api.jobs[9]["worker_id"] = "someone-else"
    world.clock.moment = START + dt.timedelta(hours=3)

    world.run()

    assert world.ledger()["jobs"]["9"]["state"] == "lost"
    assert len(world.calls()) == 1


# -- quota handling ----------------------------------------------------------

def test_quota_wait_keeps_claim_and_resumes_same_provider_after_reset(world):
    world.config["repositories"][REPO]["providers"] = ["claude"]
    world.api.add(11)
    world.plan(claude=QUOTA)

    first = world.run()[1]
    assert (first["status"], first["next_retry_at"]) == ("waiting_provider", "2026-09-27T13:00:00+00:00")
    assert [status for _, status, _ in world.api.transitions] == ["running"]
    assert world.api.jobs[11]["status"] == "running"

    world.clock.moment = START + dt.timedelta(minutes=30)
    before_reset = world.run()[1]
    assert before_reset["status"] == "all_providers_unavailable"
    assert world.api.claims == 1

    world.plan(claude=done_receipt())
    world.clock.moment = START + dt.timedelta(hours=1, minutes=1)
    after_reset = world.run()[1]
    assert after_reset["status"] == "done"
    assert [call["provider"] for call in world.calls()] == ["claude", "claude"]
    assert world.calls()[1]["resume"] == "1"


def test_resume_after_quota_is_blocked_by_uncommitted_drift(world):
    world.config["repositories"][REPO]["providers"] = ["claude"]
    world.api.add(12)
    world.plan(claude=QUOTA)
    world.run()
    (world.worktree / "drift.txt").write_text("edited while the provider was away")
    world.plan(claude=done_receipt())
    world.clock.moment = START + dt.timedelta(hours=1, minutes=1)

    result = world.run()[1]

    assert (result["status"], result["reason"]) == ("blocked", "worktree_changed_while_waiting")
    assert len(world.calls()) == 1


def test_other_work_uses_available_provider_without_moving_waiting_job(world):
    world.api.add(21)
    world.api.add(22)
    world.plan(claude=QUOTA, codex=done_receipt("ready_for_review"))

    world.run()
    second = world.run()[1]

    assert second["job_id"] == 22
    jobs = world.ledger()["jobs"]
    assert (jobs["21"]["state"], jobs["21"]["provider"]) == ("waiting_provider", "claude")
    assert (jobs["22"]["state"], jobs["22"]["provider"]) == ("ready_for_review", "codex")


def test_all_providers_unavailable_exits_cleanly_with_retry_and_no_claim(world):
    world.api.add(31)
    state = world.home / "state"
    state.mkdir()
    (state / "ledger.json").write_text(json.dumps({"version": 1, "jobs": {}, "intent": None, "halt": None,
        "providers": {"claude": {"unavailable_until": "2026-09-27T14:00:00+00:00"},
            "codex": {"unavailable_until": "2026-09-27T13:30:00+00:00"}}}))

    code, result = world.run()

    assert (code, result["status"], result["next_retry_at"]) == (0, "all_providers_unavailable",
        "2026-09-27T13:30:00+00:00")
    assert world.api.claims == 0
    assert world.calls() == []


def test_task_failure_is_not_a_provider_cooldown(world):
    world.api.add(41)
    world.plan(claude={"exit": 2})

    result = world.run()[1]

    assert result["status"] == "failed"
    assert world.api.transitions[-1][1] == "failed"
    assert world.ledger()["providers"] == {}


# -- no accidental done --------------------------------------------------------

def test_exit_zero_without_receipt_never_marks_done(world):
    world.api.add(51)
    world.plan(claude={"exit": 0})

    code, result = world.run()

    assert (code, result["reason"]) == (3, "exit_zero_without_receipt")
    assert "done" not in [status for _, status, _ in world.api.transitions]


def test_exit_zero_with_failed_validation_never_marks_done(world):
    world.api.add(52)
    world.plan(claude=done_receipt(passed=False))

    assert world.run()[1]["reason"] == "receipt_validation_not_passed"
    assert "done" not in [status for _, status, _ in world.api.transitions]


def test_receipt_for_another_revision_is_rejected(world):
    world.api.add(53)
    world.plan(claude={"exit": 0, "receipt": {"phase": "done", "revision": "0" * 40, "validation": PASSED}})

    assert world.run()[1]["reason"] == "receipt_revision_mismatch"


def test_stale_receipt_from_another_attempt_is_rejected(world):
    world.api.add(56)
    world.plan(claude={"exit": 0, "receipt": {**done_receipt()["receipt"], "attempt_nonce": "stale-nonce"}})

    assert world.run()[1]["reason"] == "receipt_attempt_mismatch"
    assert "done" not in world.statuses()


def test_receipt_for_another_worktree_is_rejected(world):
    world.api.add(57)
    world.plan(claude={"exit": 0, "receipt": {**done_receipt()["receipt"], "worktree": "/somewhere/else"}})

    assert world.run()[1]["reason"] == "receipt_worktree_mismatch"
    assert "done" not in world.statuses()


@pytest.mark.parametrize("validation, reason", [
    ({"passed": True}, "receipt_validation_commands_missing"),
    ({"passed": True, "commands": ["pytest"]}, "receipt_validation_commands_missing"),
    ({"passed": True, "commands": [{"command": "pytest", "exit_code": 1}]}, "receipt_validation_command_failed"),
    ({"passed": True, "commands": [{"command": "pytest", "exit_code": False}]}, "receipt_validation_command_failed"),
])
def test_receipt_needs_explicit_passing_validation_command_records(world, validation, reason):
    world.api.add(58)
    world.plan(claude={"exit": 0, "receipt": {"phase": "done", "validation": validation}})

    assert world.run()[1]["reason"] == reason
    assert "done" not in world.statuses()


def test_receipt_beside_unrecorded_dirty_worktree_is_rejected(world):
    world.api.add(59)
    world.plan(claude={**done_receipt(), "touch": "scratch.txt"})

    assert world.run()[1]["reason"] == "receipt_worktree_dirty"
    assert "done" not in world.statuses()


def test_ai_written_done_phase_never_closes_issue_without_audited_launcher(world):
    del world.config["repositories"][REPO]["done_supported"]
    world.api.add(60)
    world.plan(claude=done_receipt())

    code, result = world.run()

    assert (code, result["reason"]) == (3, "done_requires_audited_launcher")
    assert "done" not in world.statuses()
    assert world.api.jobs[60]["status"] == "running"
    assert world.ledger()["jobs"]["60"]["state"] == "blocked"


def test_ready_for_review_retains_claim_and_is_not_issue_done(world):
    world.api.add(54)
    world.plan(claude=done_receipt("ready_for_review"))

    result = world.run()[1]

    assert result["status"] == "ready_for_review"
    assert world.api.jobs[54]["status"] == "running"
    assert world.run()[1]["status"] == "idle"
    assert len(world.calls()) == 1


def test_review_claim_closed_elsewhere_is_never_reported_done_by_bridge(world):
    world.api.add(65)
    world.plan(claude=done_receipt("ready_for_review"))
    world.run()
    world.api.jobs[65]["status"] = "done"  # a human or verified reconciler closed it after merge

    world.run()

    record = world.ledger()["jobs"]["65"]
    assert record["state"] == "lost"
    assert "outcome not verified" in record["reason"]
    assert "done" not in world.statuses()


def test_validated_done_receipt_reports_done(world):
    world.api.add(55)
    world.plan(claude=done_receipt())

    world.run()

    job_id, status, receipt = world.api.transitions[-1]
    assert (job_id, status, receipt["validation"]["passed"]) == (55, "done", True)


# -- ownership and scope --------------------------------------------------------

def test_registration_mismatch_blocks_before_claim(world):
    world.api = FakeApi(served=(REPO, "owner/Other"))
    world.api.add(61)

    code, result = world.run()

    assert (code, result["reason"]) == (3, "registration_mismatch")
    assert world.api.claims == 0


def test_contested_job_is_rejected_and_never_launched(world):
    world.api.add(62, contested=True)

    code, result = world.run()

    assert (code, result["reason"]) == (3, "contested_job_rejected")
    assert world.calls() == []
    assert world.api.transitions == []


def test_claim_owned_by_another_worker_is_rejected(world):
    world.api.add(63)
    original = world.api.claim

    def foreign_claim():
        job = original()
        job["worker_id"] = "nas-02"
        return job

    world.api.claim = foreign_claim

    assert world.run()[1]["reason"] == "ownership_mismatch"
    assert world.calls() == []


# -- explicit handoff -----------------------------------------------------------

def write_evidence(world, job_id, **overrides):
    record = world.ledger()["jobs"][str(job_id)]
    evidence = {"from_provider": record["provider"], "worktree": str(world.worktree), "revision": record["revision"],
        "phase": record["phase"], "attempt": record["attempts"], "worktree_digest": record["checkpoint_digest"],
        "validation": PASSED, **overrides}
    path = world.home / f"handoff-{job_id}.json"
    path.write_text(json.dumps(evidence))
    return str(path)


def quota_then_evidence(world, **overrides):
    world.api.add(71)
    world.plan(claude=QUOTA, codex=done_receipt())
    world.run()
    return write_evidence(world, 71, **overrides)


def test_handoff_is_rejected_when_launcher_does_not_support_it(world):
    evidence = quota_then_evidence(world)

    code, result = world.run("handoff", job="71", to="codex", evidence=evidence)

    assert code == 3
    assert result["reason"].startswith("handoff_unsupported_by_launcher")
    assert "resume with claude" in result["reason"]
    world.clock.moment = START + dt.timedelta(minutes=5)
    assert world.run()[1]["status"] != "done"
    assert [call["provider"] for call in world.calls()] == ["claude"]


def test_handoff_requires_old_process_gone_and_same_revision(world):
    world.config["repositories"][REPO]["handoff_supported"] = True
    evidence = quota_then_evidence(world)
    world.alive = lambda pid: True
    world.ledger_path = world.home / "state" / "ledger.json"
    ledger = world.ledger()
    ledger["jobs"]["71"]["pid"] = 4242
    world.ledger_path.write_text(json.dumps(ledger))
    assert world.run("handoff", job="71", to="codex", evidence=evidence)[1]["reason"] == "handoff_old_process_alive"

    world.alive = lambda pid: False
    subprocess.run(world.git + ["commit", "-q", "--allow-empty", "-m", "drift"], check=True)
    assert world.run("handoff", job="71", to="codex", evidence=evidence)[1]["reason"] == "handoff_revision_mismatch"


def test_handoff_without_recorded_validation_is_rejected(world):
    world.config["repositories"][REPO]["handoff_supported"] = True
    evidence = quota_then_evidence(world, validation={"passed": False})

    assert world.run("handoff", job="71", to="codex", evidence=evidence)[1]["reason"] == \
        "handoff_validation_not_recorded"


@pytest.mark.parametrize("validation", [{"passed": True}, {"passed": True, "commands": ["pytest"]}])
def test_handoff_without_validation_command_records_is_rejected(world, validation):
    world.config["repositories"][REPO]["handoff_supported"] = True
    evidence = quota_then_evidence(world, validation=validation)

    assert world.run("handoff", job="71", to="codex", evidence=evidence)[1]["reason"] == \
        "handoff_validation_not_recorded"


def test_handoff_rejects_unrecorded_dirty_drift_at_same_head(world):
    world.config["repositories"][REPO]["handoff_supported"] = True
    evidence = quota_then_evidence(world)
    (world.worktree / "drift.txt").write_text("edited after the checkpoint")

    assert world.run("handoff", job="71", to="codex", evidence=evidence)[1]["reason"] == \
        "handoff_worktree_state_mismatch"


def test_handoff_rejects_evidence_for_another_checkpoint_or_attempt(world):
    world.config["repositories"][REPO]["handoff_supported"] = True
    evidence = quota_then_evidence(world, worktree_digest="0" * 64)
    assert world.run("handoff", job="71", to="codex", evidence=evidence)[1]["reason"] == \
        "handoff_worktree_state_mismatch"

    evidence = write_evidence(world, 71, attempt=99)
    assert world.run("handoff", job="71", to="codex", evidence=evidence)[1]["reason"] == "handoff_attempt_mismatch"


def test_handoff_preserves_dirty_checkpoint_and_continues_it(world):
    world.config["repositories"][REPO]["handoff_supported"] = True
    world.api.add(72)
    world.plan(claude={**QUOTA, "touch": "wip.txt"}, codex={**done_receipt(), "commit": True})
    world.run()
    assert world.ledger()["jobs"]["72"]["checkpoint_clean"] is False
    evidence = write_evidence(world, 72)

    assert world.run("handoff", job="72", to="codex", evidence=evidence)[1]["status"] == "handoff_recorded"
    result = world.run()[1]

    assert result["status"] == "done"
    tracked = subprocess.run(world.git[:3] + ["ls-files", "wip.txt"], capture_output=True, text=True).stdout
    assert tracked.strip() == "wip.txt"


def test_explicit_valid_handoff_continues_same_worktree_on_new_provider(world):
    world.config["repositories"][REPO]["handoff_supported"] = True
    evidence = quota_then_evidence(world)

    assert world.run("handoff", job="71", to="codex", evidence=evidence)[1]["status"] == "handoff_recorded"
    result = world.run()[1]

    assert result["status"] == "done"
    assert [call["provider"] for call in world.calls()] == ["claude", "codex"]
    assert world.ledger()["jobs"]["71"]["handoffs"][0]["to_provider"] == "codex"


# -- secrets and host scope ---------------------------------------------------------

def test_api_refuses_to_send_token_to_another_host():
    client = bridge.Api("http://127.0.0.1:9/api", "super-secret-token")
    client.base_url = "http://attacker.example/api"
    with pytest.raises(bridge.BridgeError, match="escaped"):
        client.request("GET", "/worker/me")


@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
def test_api_refuses_redirects_so_the_token_never_follows(server, code):
    elsewhere = server({("GET", "/api/worker/me"): (200, {}, {"worker_id": "attacker"})})
    origin = server({("GET", "/api/worker/me"): (code, {"Location": base(elsewhere) + "/worker/me"}, None)})
    client = bridge.Api(base(origin), "super-secret-token")

    with pytest.raises(bridge.BridgeError, match="redirect"):
        client.me()

    assert elsewhere.seen == []
    assert len(origin.seen) == 1


def test_api_ignores_environment_proxies(server, monkeypatch):
    target = server({("GET", "/api/worker/me"): (200, {}, {"worker_id": WORKER, "served_repos": []})})
    proxy = server({})
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
    for name in ("http_proxy", "HTTP_PROXY"):
        monkeypatch.setenv(name, f"http://127.0.0.1:{proxy.server_address[1]}")

    assert bridge.Api(base(target), "super-secret-token").me()["worker_id"] == WORKER
    assert proxy.seen == []
    assert target.seen[0]["authorization"] == "Bearer super-secret-token"


def test_cli_output_never_contains_the_token(world, capsys):
    path = world.home / "config.json"
    path.write_text(json.dumps(world.config))

    code = bridge.main(["tick", "--config", str(path)])

    output = capsys.readouterr().out
    assert code == 1
    assert json.loads(output)["status"] == "error"
    assert "super-secret-token" not in output


def test_launcher_environment_does_not_receive_the_token(world):
    world.api.add(81)
    world.config["repositories"][REPO]["launch"]["claude"] = [sys.executable, "-c",
        "import os,sys; sys.exit(9 if 'NIGHTCREW_TOKEN' in os.environ else 2)"]

    world.run()

    assert world.api.transitions[-1][2]["exit_code"] == 2


# -- observation-only ticks -------------------------------------------------------

@pytest.mark.parametrize("setting", ["missing", False, "true", 1])
def test_tick_without_explicit_dispatch_enabled_only_observes(world, setting):
    del world.config["dispatch_enabled"]
    if setting != "missing":
        world.config["dispatch_enabled"] = setting
    world.api.add(101)
    world.plan(claude=done_receipt())

    code, result = world.run()

    assert (code, result["status"], result["observe_reason"]) == (0, "observed", "dispatch_not_enabled")
    assert result["dispatch_enabled"] is False
    assert world.api.requests == ["GET /worker/me", "GET /worker/jobs"]
    assert world.calls() == []
    assert not (world.home / "state").exists()


def test_observe_flag_reports_held_jobs_without_mutation_or_fence_token(world):
    world.api.add(102)
    world.plan(claude=QUOTA)
    world.run()
    world.api.jobs[102]["claim_token"] = "fence-secret"
    world.api.jobs[103] = {"id": 103, "repo": REPO, "kind": "issue", "reference": "103", "status": "claimed",
        "worker_id": WORKER, "claim_token": "other-fence"}
    ledger_before = (world.home / "state" / "ledger.json").read_text()
    world.api.requests.clear()
    world.clock.moment = START + dt.timedelta(hours=3)

    code, result = world.run(observe=True)

    assert (code, result["observe_reason"], result["dispatch_enabled"]) == (0, "observe_flag", True)
    assert result["held_jobs"] == [
        {"id": 102, "repo": REPO, "kind": "issue", "reference": "102", "status": "running", "worker_id": WORKER,
            "in_ledger": True},
        {"id": 103, "repo": REPO, "kind": "issue", "reference": "103", "status": "claimed", "worker_id": WORKER,
            "in_ledger": False}]
    assert result["unknown_held_jobs"] == [103]
    assert result["ledger_active_jobs"] == [{"id": 102, "state": "waiting_provider", "provider": "claude"}]
    assert "fence" not in json.dumps(result)
    assert world.api.requests == ["GET /worker/me", "GET /worker/jobs"]
    assert (world.home / "state" / "ledger.json").read_text() == ledger_before
    assert len(world.calls()) == 1


def test_observe_reports_registration_mismatch_without_writing_a_halt(world):
    world.api = FakeApi(served=(REPO, "owner/Other"))

    code, result = world.run(observe=True)

    assert (code, result["registration"]["matches"]) == (3, False)
    assert not (world.home / "state").exists()


def test_observe_cli_over_http_sends_only_gets_with_stable_output(world, server, capsys):
    httpd = server({
        ("GET", "/api/worker/me"): (200, {}, {"worker_id": WORKER, "served_repos": [REPO]}),
        ("GET", "/api/worker/jobs"): (200, {}, {"data": [{"id": 5, "repo": REPO, "kind": "issue", "reference": "5",
            "status": "claimed", "worker_id": WORKER, "claim_token": "fence-secret"}]})})
    world.config["api_base"] = base(httpd)
    path = world.home / "config.json"
    path.write_text(json.dumps(world.config))

    code = bridge.main(["tick", "--observe", "--config", str(path)])

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert (code, payload["status"], payload["unknown_held_jobs"]) == (0, "observed", [5])
    assert output == json.dumps(payload, sort_keys=True) + "\n"
    assert [entry["method"] for entry in httpd.seen] == ["GET", "GET"]
    assert "super-secret-token" not in output
    assert "fence-secret" not in output
