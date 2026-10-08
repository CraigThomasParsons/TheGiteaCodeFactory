"""Outside-in tests for scripts/coach.py.

Contract: --config, --packet, --event, --state and --output files. On a
confirmed rate limit with the old writer stopped, it benches the current
account in the state ledger, writes a handoff packet to --output (picking the
first eligible agent in config order, or parking) and prints a one-line JSON
summary. Any refusal exits 1 with the reason on stderr and writes nothing.
"""

import fcntl
import json
import stat
import time
import unittest
from datetime import datetime, timezone

from support import HelperTestCase, base_env, run_tool

FUTURE = "2030-01-01T00:00:00Z"
FUTURE_TS = datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp()


def agent(id, account, **extra):
    value = {"id": id, "account": account, "enabled": True, "installed": True, "capabilities": ["IMPL", "REVIEW"]}
    value.update(extra)
    return value


PACKET = {"task": "https://gitea.example/o/r/issues/1", "repo": "o/r", "branch": "feat/x",
          "worktree": "/work/x", "phase": "IMPL", "head_sha": "a" * 40, "evidence": ["log.txt"],
          "agent": "codex-a", "attempted_accounts": []}


class CoachTest(HelperTestCase):
    def setUp(self):
        super().setUp()
        self.config = {"agents": [agent("codex-a", "acct-a"), agent("claude-b", "acct-b"), agent("gemini-c", "acct-c")]}
        self.packet = dict(PACKET)
        self.event = {"kind": "rate_limited", "writer_stopped": True, "agent": "codex-a", "reset_at": FUTURE}
        self.state = self.tmp / "state" / "ledger.json"
        self.output = self.tmp / "out" / "handoff.json"

    def route(self):
        config = self.write_json("config.json", self.config)
        packet = self.write_json("packet.json", self.packet)
        event = self.write_json("event.json", self.event)
        return run_tool("coach", ["--config", config, "--packet", packet, "--event", event,
                                  "--state", self.state, "--output", self.output], env=base_env(self.home))

    def ok(self):
        result = self.route()
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout), json.loads(self.output.read_text()), json.loads(self.state.read_text())

    def refused(self, message=None):
        result = self.route()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        if message is not None:
            self.assertEqual(result.stderr, message + "\n")
        self.assertFalse(self.output.exists())
        return result

    def test_handoff_ready_to_next_agent_in_config_order(self):
        summary, handoff, ledger = self.ok()
        self.assertEqual(summary, {"status": "handoff_ready", "agent": "claude-b", "handoff": str(self.output)})
        expected = dict(PACKET, agent="claude-b", previous_agent="codex-a", attempted_accounts=["acct-a"],
                        status="handoff_ready", reason="rate_limited", benched_until="2030-01-01T00:00:00+00:00")
        self.assertEqual(handoff, expected)
        self.assertEqual(set(ledger), {"acct-a"})
        self.assertEqual(ledger["acct-a"]["until"], FUTURE_TS)
        self.assertEqual(ledger["acct-a"]["failures"], 1)
        self.assertAlmostEqual(ledger["acct-a"]["observed_at"], time.time(), delta=60)

    def test_files_are_private_and_end_with_newline(self):
        self.ok()
        for path in (self.state, self.output):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path)
            self.assertTrue(path.read_text().endswith("}\n"))
        self.assertTrue(self.state.with_suffix(".lock").exists())

    def test_parked_when_no_candidate(self):
        self.config["agents"] = [agent("codex-a", "acct-a")]
        summary, handoff, _ = self.ok()
        self.assertEqual(summary, {"status": "parked", "agent": None, "handoff": str(self.output)})
        self.assertIsNone(handoff["agent"])
        self.assertEqual(handoff["status"], "parked")

    def test_ineligible_candidates_are_skipped(self):
        self.config["agents"] = [
            agent("codex-a", "acct-a"),
            agent("off", "acct-1", enabled=False),
            agent("truthy", "acct-2", enabled="yes"),
            agent("missing", "acct-3", installed=False),
            agent("reviewer", "acct-4", capabilities=["REVIEW"]),
            agent("tried", "acct-5"),
            agent("same-account", "acct-a"),
            agent("benched", "acct-6"),
            agent("fine", "acct-7"),
        ]
        self.packet["attempted_accounts"] = ["acct-5"]
        self.state.parent.mkdir(parents=True)
        self.state.write_text(json.dumps({"acct-6": {"until": FUTURE_TS, "failures": 1, "observed_at": 0}}))
        summary, handoff, ledger = self.ok()
        self.assertEqual(summary["agent"], "fine")
        self.assertEqual(handoff["attempted_accounts"], ["acct-5", "acct-a"])
        self.assertEqual(ledger["acct-6"]["until"], FUTURE_TS)

    def test_expired_bench_is_eligible_again(self):
        self.state.parent.mkdir(parents=True)
        self.state.write_text(json.dumps({"acct-b": {"until": 1000, "failures": 4, "observed_at": 0}}))
        summary, _, ledger = self.ok()
        self.assertEqual(summary["agent"], "claude-b")
        self.assertEqual(ledger["acct-b"], {"until": 1000, "failures": 4, "observed_at": 0})

    def test_attempted_accounts_are_deduplicated_in_order(self):
        self.packet["attempted_accounts"] = ["acct-x", "acct-a", "acct-x"]
        _, handoff, _ = self.ok()
        self.assertEqual(handoff["attempted_accounts"], ["acct-x", "acct-a"])

    def test_backoff_without_reset_time(self):
        del self.event["reset_at"]
        before = time.time()
        _, handoff, ledger = self.ok()
        self.assertAlmostEqual(ledger["acct-a"]["until"], before + 60, delta=30)
        benched = datetime.fromisoformat(handoff["benched_until"])
        self.assertAlmostEqual(benched.timestamp(), ledger["acct-a"]["until"], delta=0.001)

    def test_backoff_doubles_with_failures_and_caps_at_six_hours(self):
        del self.event["reset_at"]
        for previous_failures, delay in [(1, 120), (3, 480), (9, 21600), (20, 21600)]:
            with self.subTest(previous_failures=previous_failures):
                self.state.parent.mkdir(parents=True, exist_ok=True)
                self.state.write_text(json.dumps({"acct-a": {"until": 0, "failures": previous_failures}}))
                self.output.unlink(missing_ok=True)
                before = time.time()
                _, _, ledger = self.ok()
                self.assertEqual(ledger["acct-a"]["failures"], previous_failures + 1)
                self.assertAlmostEqual(ledger["acct-a"]["until"], before + delay, delta=30)

    def test_longer_existing_bench_is_kept(self):
        later = FUTURE_TS + 86400
        self.state.parent.mkdir(parents=True)
        self.state.write_text(json.dumps({"acct-a": {"until": later, "failures": 2}}))
        _, handoff, ledger = self.ok()
        self.assertEqual(ledger["acct-a"]["until"], later)
        self.assertEqual(handoff["benched_until"], "2030-01-02T00:00:00+00:00")

    def test_offset_reset_time(self):
        self.event["reset_at"] = "2030-01-01T02:00:00+02:00"
        _, handoff, _ = self.ok()
        self.assertEqual(handoff["benched_until"], "2030-01-01T00:00:00+00:00")

    def test_refusals(self):
        cases = [
            ({"kind": "crashed"}, "Only confirmed rate-limit events authorize automatic failover"),
            ({"writer_stopped": False}, "Reconcile the old writer before transferring ownership"),
            ({"writer_stopped": "true"}, "Reconcile the old writer before transferring ownership"),
            ({"agent": "claude-b"}, "Rate-limit event does not identify the current agent"),
            ({"reset_at": "2030-01-01T00:00:00"}, "reset_at must include a timezone"),
            ({"reset_at": "2001-01-01T00:00:00Z"}, "Reset time must be in the future"),
        ]
        original = dict(self.event)
        for change, message in cases:
            with self.subTest(change=change):
                self.event = dict(original, **change)
                self.refused(message)
                self.assertFalse(self.state.exists())

    def test_packet_must_be_complete(self):
        for key in ("task", "repo", "branch", "worktree", "phase", "head_sha", "evidence", "agent", "attempted_accounts"):
            with self.subTest(key=key):
                self.packet = {k: v for k, v in PACKET.items() if k != key}
                self.refused("Handoff packet missing " + key)

    def test_unknown_current_agent(self):
        self.packet["agent"] = "nobody"
        self.event["agent"] = "nobody"
        self.refused("Rate-limit event does not identify the current agent")

    def test_existing_output_is_never_overwritten(self):
        self.output.parent.mkdir(parents=True)
        self.output.write_text("earlier handoff")
        result = self.route()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "Output exists; reconcile that handoff instead of routing twice\n")
        self.assertEqual(self.output.read_text(), "earlier handoff")
        self.assertFalse(self.state.exists())

    def test_held_lock_refuses(self):
        self.state.parent.mkdir(parents=True)
        with self.state.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.refused()
        self.assertFalse(self.state.exists())

    def test_unreadable_input_is_refused(self):
        self.write_json("config.json", {})
        result = run_tool("coach", ["--config", self.tmp / "missing.json", "--packet", self.tmp / "missing.json",
                                    "--event", self.tmp / "missing.json", "--state", self.state,
                                    "--output", self.output], env=base_env(self.home))
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.output.exists())

    def test_all_arguments_required(self):
        result = run_tool("coach", ["--config", "c.json"], env=base_env(self.home), cwd=self.tmp)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
