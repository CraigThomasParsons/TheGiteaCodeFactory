"""Outside-in tests for skills/retalk-bridge/scripts/retalk_bridge.py.

Contract: the bridge reads a JSON config (RETALK_BRIDGE_CONFIG), drains each
side's retalk mailbox into a private spool, injects new messages into live
Claude Code / Codex sessions through lifecycle hooks, and on `tick` wakes an
idle side non-interactively, sending the agent's final answer back over
retalk. It must back off on provider limits, never retry a message forever,
and merge its hooks into existing CLI settings without disturbing others.

Every external program (retalk, claude, codex) is a stub that records its
arguments; no network or model is used.
"""

import json
import os
import time
import unittest

from support import HelperTestCase, base_env, run_tool, write_executable

FAKE_RETALK = r'''#!/usr/bin/env python3
import json, os, sys, uuid
fake = os.environ["FAKE_DIR"]
args = sys.argv[1:]
cmd = args[0]
def opt(name):
    return args[args.index(name) + 1] if name in args else None
ident = os.path.basename(opt("--dir"))
with open(os.path.join(fake, "retalk-calls.jsonl"), "a") as log:
    log.write(json.dumps(args) + "\n")
if cmd == "receive":
    box = os.path.join(fake, ident + ".inbox")
    if os.path.exists(box):
        sys.stdout.write(open(box).read())
        os.remove(box)
elif cmd == "send":
    if os.path.exists(os.path.join(fake, "retalk-send.fail")):
        sys.stderr.write("relay unreachable\n")
        sys.exit(1)
    mid = uuid.uuid4().hex
    with open(os.path.join(fake, "sent.jsonl"), "a") as out:
        out.write(json.dumps({"from": ident, "peer": opt("--peer"), "text": args[-1], "id": mid}) + "\n")
    print(json.dumps({"id": mid, "to": opt("--peer")}))
'''

FAKE_AGENT = r'''#!/usr/bin/env python3
import json, os, sys
fake = os.environ["FAKE_DIR"]
name = os.path.basename(sys.argv[0])
with open(os.path.join(fake, name + "-calls.jsonl"), "a") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(),
                          "child": os.environ.get("RETALK_BRIDGE_CHILD")}) + "\n")
during = os.path.join(fake, name + ".during")
if os.path.exists(during):
    # A live session's prompt hook firing while this watcher run is in progress.
    import subprocess
    spec = json.load(open(during))
    env = {k: v for k, v in os.environ.items() if k != "RETALK_BRIDGE_CHILD"}
    payload = json.dumps({"session_id": "live-1", "cwd": spec["cwd"], "hook_event_name": "UserPromptSubmit"})
    hook = subprocess.run([sys.executable, spec["bridge"], "hook", "--side", spec["side"]], input=payload, env=env,
                          capture_output=True, text=True)
    with open(os.path.join(fake, name + ".during-out"), "w") as out:
        json.dump({"stdout": hook.stdout, "spool": json.load(open(spec["spool"]))}, out)
mode_file = os.path.join(fake, name + ".mode")
mode = open(mode_file).read().strip() if os.path.exists(mode_file) else "ok"
reply = open(os.path.join(fake, name + ".reply")).read() if os.path.exists(os.path.join(fake, name + ".reply")) else "pong"
if name == "claude":
    if mode == "ok":
        print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": reply, "session_id": "claude-sess-1"}))
    elif mode == "limit":
        print(json.dumps({"type": "result", "subtype": "success", "is_error": True,
                          "result": "You've hit your session limit \u00b7 resets 5:20pm (America/Toronto)", "session_id": "claude-sess-1"}))
        sys.exit(1)
    else:
        sys.stderr.write("boom\n")
        sys.exit(1)
else:
    print(json.dumps({"type": "thread.started", "thread_id": "codex-thread-1"}))
    if mode == "ok":
        print(json.dumps({"type": "item.completed", "item": {"id": "i0", "type": "agent_message", "text": reply}}))
        print(json.dumps({"type": "turn.completed", "usage": {}}))
    elif mode == "limit":
        print(json.dumps({"type": "error", "message": "You've hit your usage limit. Try again in 2h 5m."}))
        print(json.dumps({"type": "turn.failed", "error": {"message": "You've hit your usage limit. Try again in 2h 5m."}}))
        sys.exit(1)
    else:
        sys.stderr.write("boom\n")
        sys.exit(1)
'''


class RetalkBridgeTest(HelperTestCase):
    def setUp(self):
        super().setUp()
        self.fake = self.tmp / "fake"
        self.fake.mkdir()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        write_executable(self.bin / "retalk", FAKE_RETALK)
        write_executable(self.bin / "claude", FAKE_AGENT)
        write_executable(self.bin / "codex", FAKE_AGENT)
        self.live = self.tmp / "live"
        self.live.mkdir()
        self.config = {
            "retalk": str(self.bin / "retalk"),
            "state_dir": str(self.tmp / "state"),
            "codex_sessions_dir": str(self.tmp / "codex-sessions"),
            "max_hops": 2,
            "max_resumes_per_hour": 4,
            "sides": {
                "claude": {"cli": "claude", "binary": str(self.bin / "claude"), "identity_dir": str(self.tmp / "ids/me-claude"),
                           "peer": "me-codex", "auto_resume": True, "hook_cwds": [str(self.live)]},
                "codex": {"cli": "codex", "binary": str(self.bin / "codex"), "identity_dir": str(self.tmp / "ids/me-codex"),
                          "peer": "me-claude", "auto_resume": True, "hook_cwds": [str(self.live)]},
            },
        }

    # -- helpers ---------------------------------------------------------
    def bridge(self, *args, stdin=None, extra_env=None):
        self.write_json("config.json", self.config)
        env = base_env(self.home, {"RETALK_BRIDGE_CONFIG": str(self.tmp / "config.json"), "FAKE_DIR": str(self.fake)})
        if extra_env:
            env.update(extra_env)
        return run_tool("retalk_bridge", list(args), env=env, stdin=stdin)

    def deliver(self, identity, mid, text):
        with open(self.fake / (identity + ".inbox"), "a") as box:
            box.write(json.dumps({"id": mid, "from": "f" * 32, "name": "peer", "text": text}) + "\n")

    def calls(self, name):
        path = self.fake / (name + "-calls.jsonl")
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def sent(self):
        path = self.fake / "sent.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def spool(self, side):
        return json.loads((self.tmp / "state" / side / "spool.json").read_text())

    def health(self, side):
        return json.loads((self.tmp / "state" / side / "health.json").read_text())

    def events(self, side):
        path = self.tmp / "state" / side / "bridge.log"
        return [json.loads(line)["event"] for line in path.read_text().splitlines()]

    # -- watcher ---------------------------------------------------------
    def test_tick_wakes_idle_side_and_sends_reply_once(self):
        self.deliver("me-codex", "m1", "reply with the word pong")
        result = self.bridge("tick")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls("codex")
        self.assertEqual(len(calls), 1)
        argv = calls[0]["argv"]
        self.assertEqual(argv[:2], ["exec", "--json"])
        self.assertIn("read-only", argv)
        self.assertIn("reply with the word pong", argv[-1])
        self.assertIn("message m1 from peer", argv[-1])
        self.assertEqual(calls[0]["child"], "1")
        self.assertEqual(self.sent(), [{"from": "me-codex", "peer": "me-claude", "text": "[retalk-bridge hop=1] pong", "id": self.sent()[0]["id"]}])
        self.assertEqual([e["status"] for e in self.spool("codex")], ["answered"])
        self.assertEqual(self.calls("claude"), [])
        # A second pass has nothing new: no model call, no send.
        self.bridge("tick")
        self.assertEqual(len(self.calls("codex")), 1)
        self.assertEqual(len(self.sent()), 1)

    def test_next_wake_resumes_the_bridge_session(self):
        self.deliver("me-codex", "m1", "first")
        self.bridge("tick", "--side", "codex")
        self.deliver("me-codex", "m2", "second")
        self.bridge("tick", "--side", "codex")
        argv = self.calls("codex")[1]["argv"]
        self.assertEqual(argv[:4], ["exec", "resume", "codex-thread-1", "--json"])

    def test_inbox_file_mode_reads_without_receiving(self):
        inbox = self.tmp / "agent-talk-inbox.ndjson"
        self.config["sides"]["codex"].update(inbox_file=str(inbox), inbox_since="2026-10-17T01:43:00Z", peer_fingerprint="f" * 32)
        lines = [
            {"id": "old", "from": "f" * 32, "name": "me-claude", "text": "before install", "ts": "2026-10-17T01:00:00Z"},
            {"id": "m1", "from": "f" * 32, "name": "me-claude", "text": "ping", "ts": "2026-10-17T01:43:56Z"},
            {"id": "o1", "from": "e" * 32, "name": "someone", "text": "not my peer", "ts": "2026-10-17T01:44:00Z"},
        ]
        inbox.write_text("".join(json.dumps(line) + "\n" for line in lines) + '{"id": "partial"')
        self.deliver("me-codex", "relay-only", "must stay on the relay")
        self.bridge("tick", "--side", "codex")
        self.assertEqual([e["id"] for e in self.spool("codex")], ["m1"])
        self.assertTrue((self.fake / "me-codex.inbox").exists(), "retalk receive must not be called in inbox mode")
        self.assertEqual(len(self.calls("codex")), 1)
        self.assertEqual(self.sent()[0]["text"], "[retalk-bridge hop=1] pong")
        # The half-written line is completed later and then read exactly once.
        with open(inbox, "a") as out:
            out.write(', "from": "' + "f" * 32 + '", "name": "me-claude", "text": "late", "ts": "2026-10-17T02:00:00Z"}\n')
        self.bridge("fetch", "--side", "codex")
        self.bridge("fetch", "--side", "codex")
        self.assertEqual([e["id"] for e in self.spool("codex")], ["m1", "partial"])
        self.assertNotIn("duplicate_ignored", self.events("codex"))

    def test_duplicate_message_id_is_ignored(self):
        self.deliver("me-codex", "m1", "hello")
        self.bridge("fetch", "--side", "codex")
        self.deliver("me-codex", "m1", "hello")
        result = self.bridge("fetch", "--side", "codex")
        self.assertEqual(json.loads(result.stdout)["fetched"], 0)
        self.assertEqual(len(self.spool("codex")), 1)
        self.assertIn("duplicate_ignored", self.events("codex"))

    def test_rate_limit_benches_side_until_reset_and_keeps_message(self):
        (self.fake / "claude.mode").write_text("limit")
        self.deliver("me-claude", "m1", "ping")
        self.bridge("tick", "--side", "claude")
        self.assertEqual(len(self.calls("claude")), 1)
        self.assertEqual(self.sent(), [])
        health = self.health("claude")
        self.assertGreater(health["benched_until"], time.time())
        self.assertLessEqual(health["benched_until"], time.time() + 86400)
        self.assertIn("session limit", health["bench_reason"])
        entry = self.spool("claude")[0]
        self.assertEqual((entry["status"], entry["attempts"]), ("pending", 0))
        # Benched: the next passes do not call the CLI again.
        self.bridge("tick", "--side", "claude")
        self.bridge("tick", "--side", "claude")
        self.assertEqual(len(self.calls("claude")), 1)
        self.assertIn("skipped_benched", self.events("claude"))

    def test_codex_limit_uses_relative_reset(self):
        (self.fake / "codex.mode").write_text("limit")
        self.deliver("me-codex", "m1", "ping")
        before = time.time()
        self.bridge("tick", "--side", "codex")
        until = self.health("codex")["benched_until"]
        self.assertAlmostEqual(until, before + 2 * 3600 + 5 * 60, delta=30)

    def test_codex_limit_with_dated_reset(self):
        (self.fake / "codex.reply").write_text("")
        (self.fake / "codex.mode").write_text("limit")
        script = (self.bin / "codex").read_text().replace("Try again in 2h 5m.", "try again at Oct 17th, 2099 2:07 AM.")
        (self.bin / "codex").write_text(script)
        self.deliver("me-codex", "m1", "ping")
        self.bridge("tick", "--side", "codex")
        import datetime
        expected = datetime.datetime(2099, 10, 17, 2, 7).timestamp()
        self.assertAlmostEqual(self.health("codex")["benched_until"], expected, delta=1)

    def test_codex_precheck_benches_without_calling_model(self):
        day = self.tmp / "codex-sessions" / "2026" / "10" / "16"
        day.mkdir(parents=True)
        reset = int(time.time()) + 3600
        (day / "rollout.jsonl").write_text(json.dumps({"type": "event_msg", "payload": {"type": "token_count", "rate_limits": {
            "primary": {"used_percent": 100.0, "window_minutes": 300, "resets_at": reset},
            "secondary": {"used_percent": 20.0, "window_minutes": 10080, "resets_at": reset + 9999}}}}) + "\n")
        self.deliver("me-codex", "m1", "ping")
        self.bridge("tick", "--side", "codex")
        self.assertEqual(self.calls("codex"), [])
        self.assertEqual(self.health("codex")["benched_until"], reset)

    def test_failure_opens_circuit_breaker(self):
        self.config["circuit_breaker_failures"] = 1
        (self.fake / "codex.mode").write_text("crash")
        self.deliver("me-codex", "m1", "ping")
        self.bridge("tick", "--side", "codex")
        self.deliver("me-codex", "m2", "ping again")
        self.bridge("tick", "--side", "codex")
        self.assertEqual(len(self.calls("codex")), 1)
        self.assertIn("circuit_opened", self.events("codex"))
        self.assertIn("skipped_circuit_open", self.events("codex"))

    def test_hook_during_a_watcher_run_skips_the_claimed_batch(self):
        from support import tool_path
        spool = self.tmp / "state" / "codex" / "spool.json"
        (self.fake / "codex.during").write_text(json.dumps(
            {"bridge": str(tool_path("retalk_bridge")), "side": "codex", "cwd": str(self.live), "spool": str(spool)}))
        self.deliver("me-codex", "m1", "ping")
        self.bridge("tick", "--side", "codex")
        during = json.loads((self.fake / "codex.during-out").read_text())
        self.assertEqual([(e["id"], e["status"], e["attempts"]) for e in during["spool"]], [("m1", "resuming", 1)])
        self.assertEqual(during["stdout"], "", "the live hook must not deliver a batch the watcher is answering")
        self.assertEqual([e["status"] for e in self.spool("codex")], ["answered"])
        self.assertEqual(len(self.sent()), 1)

    def test_claim_left_by_a_crashed_run_is_released(self):
        self.deliver("me-codex", "m1", "ping")
        self.bridge("fetch", "--side", "codex")
        entries = self.spool("codex")
        entries[0].update(status="resuming", attempts=1)
        (self.tmp / "state" / "codex" / "spool.json").write_text(json.dumps(entries))
        self.bridge("tick", "--side", "codex")
        self.assertEqual(len(self.calls("codex")), 1)
        self.assertEqual([(e["status"], e["attempts"]) for e in self.spool("codex")], [("answered", 2)])
        self.assertIn("stale_claim_released", self.events("codex"))

    def test_failed_run_puts_the_batch_back_to_pending(self):
        self.config["circuit_breaker_failures"] = 99
        (self.fake / "codex.mode").write_text("crash")
        self.deliver("me-codex", "m1", "ping")
        self.bridge("tick", "--side", "codex")
        self.assertEqual([(e["status"], e["attempts"]) for e in self.spool("codex")], [("pending", 1)])

    def test_reply_send_failure_is_recorded_and_shown(self):
        (self.fake / "retalk-send.fail").write_text("")
        self.deliver("me-codex", "m1", "ping")
        self.bridge("tick", "--side", "codex")
        entry = self.spool("codex")[0]
        self.assertEqual(entry["status"], "reply_failed")
        self.assertIn("pong", entry["reply_summary"])
        self.assertEqual(self.health("codex")["failures"], 1)
        self.assertIn("send_failed", self.events("codex"))
        self.assertIn("reply_failed", self.events("codex"))
        # Not retried by the watcher (no second model call) but shown to the live session.
        self.bridge("tick", "--side", "codex")
        self.assertEqual(len(self.calls("codex")), 1)
        context = json.loads(self.hook("codex", "UserPromptSubmit", self.live).stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("reply NOT sent (retalk send failed): pong", context)

    def test_message_is_abandoned_after_max_attempts(self):
        self.config["max_attempts_per_message"] = 1
        self.config["circuit_breaker_failures"] = 99
        (self.fake / "codex.mode").write_text("crash")
        self.deliver("me-codex", "m1", "ping")
        self.bridge("tick", "--side", "codex")
        self.bridge("tick", "--side", "codex")
        self.assertEqual(len(self.calls("codex")), 1)
        self.assertEqual(self.spool("codex")[0]["status"], "dead")

    def test_hourly_cap(self):
        self.config["max_resumes_per_hour"] = 1
        self.deliver("me-codex", "m1", "one")
        self.bridge("tick", "--side", "codex")
        self.deliver("me-codex", "m2", "two")
        self.bridge("tick", "--side", "codex")
        self.assertEqual(len(self.calls("codex")), 1)
        self.assertIn("skipped_hourly_cap", self.events("codex"))

    def test_hop_limit_reads_but_does_not_reply(self):
        self.config["max_hops"] = 1
        self.deliver("me-claude", "m1", "[retalk-bridge hop=1] pong")
        self.bridge("tick", "--side", "claude")
        calls = self.calls("claude")
        self.assertEqual(len(calls), 1)
        self.assertIn("nothing you write now is sent", calls[0]["argv"][-1])
        self.assertEqual(self.sent(), [])
        self.assertIn("reply_suppressed_hop_limit", self.events("claude"))

    def test_message_past_hop_limit_is_held_without_model_call(self):
        self.config["max_hops"] = 1
        self.deliver("me-claude", "m1", "[retalk-bridge hop=2] again")
        self.bridge("tick", "--side", "claude")
        self.assertEqual(self.calls("claude"), [])
        self.assertEqual(self.spool("claude")[0]["status"], "held")

    def test_no_reply_answer_is_not_sent(self):
        (self.fake / "codex.reply").write_text("NO_REPLY")
        self.deliver("me-codex", "m1", "fyi")
        self.bridge("tick", "--side", "codex")
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.spool("codex")[0]["status"], "answered")

    def test_auto_resume_off_only_spools(self):
        self.config["sides"]["codex"]["auto_resume"] = False
        self.deliver("me-codex", "m1", "ping")
        self.bridge("tick")
        self.assertEqual(self.calls("codex"), [])

    # -- hooks -----------------------------------------------------------
    def hook(self, side, event, cwd, **extra):
        payload = {"session_id": "live-1", "cwd": str(cwd), "hook_event_name": event, **extra}
        return self.bridge("hook", "--side", side, stdin=json.dumps(payload), **({"extra_env": extra.pop("env")} if "env" in extra else {}))

    def test_prompt_hook_injects_new_messages_once(self):
        self.deliver("me-claude", "m1", "can you check the build?")
        result = self.hook("claude", "UserPromptSubmit", self.live)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("can you check the build?", context)
        self.assertIn("send --side claude", context)
        self.assertEqual(self.spool("claude")[0]["status"], "delivered")
        again = self.hook("claude", "UserPromptSubmit", self.live)
        self.assertEqual(again.stdout, "")
        session = json.loads((self.tmp / "state" / "claude" / "session.json").read_text())
        self.assertEqual(session["session_id"], "live-1")

    def test_stop_hook_blocks_to_continue_with_new_message(self):
        self.deliver("me-codex", "m1", "quick question")
        result = self.hook("codex", "Stop", self.live, stop_hook_active=False)
        out = json.loads(result.stdout)
        self.assertEqual(out["decision"], "block")
        self.assertIn("quick question", out["reason"])
        # The continued turn ends with stop_hook_active: no second block, and m2 waits.
        self.deliver("me-codex", "m2", "second question")
        self.assertEqual(self.hook("codex", "Stop", self.live, stop_hook_active=True).stdout, "")
        self.bridge("fetch", "--side", "codex")
        self.assertEqual([(e["id"], e["status"]) for e in self.spool("codex")], [("m1", "delivered"), ("m2", "pending")])
        out = json.loads(self.hook("codex", "UserPromptSubmit", self.live).stdout)
        self.assertIn("second question", out["hookSpecificOutput"]["additionalContext"])

    def test_hook_reply_command_carries_the_next_hop(self):
        self.deliver("me-claude", "m1", "[retalk-bridge hop=1] pong")
        context = json.loads(self.hook("claude", "UserPromptSubmit", self.live).stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("send --side claude --hop 2 --", context)
        self.assertIn("To reply, run:", context)

    def test_stop_hook_does_not_block_at_the_reply_limit(self):
        self.config["max_hops"] = 1
        self.deliver("me-codex", "m1", "[retalk-bridge hop=1] pong")
        self.assertEqual(self.hook("codex", "Stop", self.live, stop_hook_active=False).stdout, "")
        self.assertEqual(self.spool("codex")[0]["status"], "pending")
        context = json.loads(self.hook("codex", "UserPromptSubmit", self.live).stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("pong", context)
        self.assertIn("reply limit for this exchange has been reached", context)
        self.assertIn("--hop 2 --", context)

    def test_held_message_is_shown_at_next_prompt_but_never_blocks_stop(self):
        self.config["max_hops"] = 1
        self.deliver("me-claude", "m1", "[retalk-bridge hop=2] again")
        self.bridge("tick", "--side", "claude")
        self.assertEqual(self.spool("claude")[0]["status"], "held")
        self.assertEqual(self.hook("claude", "Stop", self.live, stop_hook_active=False).stdout, "")
        self.assertEqual(self.spool("claude")[0]["status"], "held")
        out = json.loads(self.hook("claude", "SessionStart", self.live).stdout)
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("again", context)
        self.assertIn("reply limit for this exchange has been reached", context)
        self.assertEqual(self.spool("claude")[0]["status"], "delivered")
        self.assertEqual(self.calls("claude"), [])

    def test_hook_outside_allowed_dirs_does_nothing(self):
        self.deliver("me-claude", "m1", "hello")
        other = self.tmp / "elsewhere"
        other.mkdir()
        result = self.hook("claude", "UserPromptSubmit", other)
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        self.assertTrue((self.fake / "me-claude.inbox").exists(), "mailbox must not be drained")

    def test_hook_inside_a_watcher_run_does_nothing(self):
        self.deliver("me-claude", "m1", "hello")
        payload = json.dumps({"session_id": "x", "cwd": str(self.live), "hook_event_name": "UserPromptSubmit"})
        result = self.bridge("hook", "--side", "claude", stdin=payload, extra_env={"RETALK_BRIDGE_CHILD": "1"})
        self.assertEqual(result.stdout, "")
        self.assertTrue((self.fake / "me-claude.inbox").exists())

    def test_watcher_answer_is_noted_in_next_live_prompt(self):
        self.deliver("me-codex", "m1", "ping")
        self.bridge("tick", "--side", "codex")
        # A turn ending with nothing new keeps the note for the next prompt.
        self.assertEqual(self.hook("codex", "Stop", self.live, stop_hook_active=False).stdout, "")
        out = json.loads(self.hook("codex", "UserPromptSubmit", self.live).stdout)
        self.assertIn("answered automatically while you were idle", out["hookSpecificOutput"]["additionalContext"])

    # -- send, usage -----------------------------------------------------
    def test_send(self):
        result = self.bridge("send", "--side", "claude", "hello codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["to"], "me-codex")
        self.assertEqual(self.sent()[0]["text"], "hello codex")
        retalk_args = json.loads((self.fake / "retalk-calls.jsonl").read_text().splitlines()[0])
        self.assertIn("--save", retalk_args)
        self.assertEqual(retalk_args[-2:], ["--", "hello codex"])

    def test_send_text_after_double_dash_may_start_with_dashes(self):
        result = self.bridge("send", "--side", "claude", "--hop", "2", "--", "--not-an-option")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.sent()[0]["text"], "[retalk-bridge hop=2] --not-an-option")

    def test_usage_errors_exit_2(self):
        self.assertEqual(self.bridge("send", "--side", "claude").returncode, 2)
        self.assertEqual(self.bridge("send", "--side", "claude", "two", "words").returncode, 2)
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.bridge("tick", "--side", "nobody").returncode, 2)
        self.assertEqual(self.bridge("frobnicate").returncode, 2)

    def test_missing_config_exits_1(self):
        env = base_env(self.home, {"RETALK_BRIDGE_CONFIG": str(self.tmp / "absent.json")})
        result = run_tool("retalk_bridge", ["status"], env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no config", result.stderr)

    # -- install ---------------------------------------------------------
    def test_install_merges_idempotently_and_uninstall_restores(self):
        existing = {"model": "x", "hooks": {"Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "node other.js"}]}],
                                            "PreCompact": [{"matcher": "", "hooks": [{"type": "command", "command": "bd prime"}]}]}}
        settings = self.write_json("claude/settings.json", existing)
        codex_hooks = self.tmp / "codex" / "hooks.json"
        args = ["--claude-settings", str(settings), "--codex-hooks", str(codex_hooks), "--command", "python3 /opt/retalk_bridge.py"]
        for _ in range(2):
            result = self.bridge("install-hooks", *args)
            self.assertEqual(result.returncode, 0, result.stderr)
        merged = json.loads(settings.read_text())
        self.assertEqual(merged["model"], "x")
        self.assertEqual(merged["hooks"]["PreCompact"], existing["hooks"]["PreCompact"])
        self.assertEqual(len(merged["hooks"]["Stop"]), 2)
        self.assertEqual(merged["hooks"]["Stop"][0], existing["hooks"]["Stop"][0])
        for event in ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"):
            ours = [g for g in merged["hooks"][event] if "retalk_bridge.py hook" in g["hooks"][0]["command"]]
            self.assertEqual(len(ours), 1, event)
        self.assertEqual(merged["hooks"]["SessionStart"][-1]["hooks"][0]["command"], "python3 /opt/retalk_bridge.py hook --side claude")
        codex = json.loads(codex_hooks.read_text())
        self.assertEqual(sorted(codex["hooks"]), ["SessionStart", "Stop", "UserPromptSubmit"])
        self.assertIn("--side codex", codex["hooks"]["Stop"][0]["hooks"][0]["command"])
        result = self.bridge("uninstall-hooks", "--claude-settings", str(settings), "--codex-hooks", str(codex_hooks))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(settings.read_text()), existing)
        self.assertEqual(json.loads(codex_hooks.read_text()), {})


class InstallScriptTest(HelperTestCase):
    """install.sh / uninstall.sh against a temporary HOME (no --watcher, so no systemd)."""

    def script(self, name, *args):
        import subprocess
        from support import tool_path
        path = tool_path("retalk_bridge").parent / name
        env = base_env(self.home)
        return subprocess.run(["bash", str(path), *args], env=env, capture_output=True, text=True, timeout=60)

    def test_install_backs_up_merges_and_uninstall_reverts(self):
        claude = self.home / ".claude" / "settings.json"
        claude.parent.mkdir()
        original = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "node keep.js"}]}]}}
        claude.write_text(json.dumps(original))
        (self.home / ".codex").mkdir()
        (self.home / ".codex" / "config.toml").write_text('model = "x"\n')
        args = ["--claude-identity", "~/.retalk/a", "--claude-peer", "a-codex", "--codex-identity", "~/.retalk/b",
                "--codex-peer", "b-claude", "--hook-cwd", str(self.tmp / "work"), "--codex-inbox", "~/inbox.ndjson"]
        first = self.script("install.sh", *args)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.script("install.sh", *args)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("keeping existing", second.stdout)
        backups = sorted(p.name for p in claude.parent.iterdir() if ".bak-retalk-bridge-" in p.name)
        self.assertGreaterEqual(len(backups), 1)
        self.assertTrue(any(".bak-retalk-bridge-" in p.name for p in (self.home / ".codex").iterdir()))
        self.assertEqual((self.home / ".codex" / "config.toml").read_text(), 'model = "x"\n')
        merged = json.loads(claude.read_text())
        self.assertEqual(len(merged["hooks"]["Stop"]), 2)
        config = json.loads((self.home / ".config" / "retalk-bridge" / "config.json").read_text())
        self.assertEqual(config["sides"]["codex"]["peer"], "b-claude")
        self.assertEqual(config["sides"]["claude"]["hook_cwds"], [str(self.tmp / "work")])
        self.assertEqual(config["sides"]["codex"]["inbox_file"], "~/inbox.ndjson")
        self.assertRegex(config["sides"]["codex"]["inbox_since"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertNotIn("inbox_file", config["sides"]["claude"])
        self.assertEqual(oct((self.home / ".config" / "retalk-bridge" / "config.json").stat().st_mode & 0o777), "0o600")
        self.assertTrue((self.home / ".local" / "share" / "retalk-bridge" / "retalk_bridge.py").exists())
        gone = self.script("uninstall.sh")
        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertEqual(json.loads(claude.read_text()), original)
        self.assertFalse((self.home / ".codex" / "hooks.json").exists())
        self.assertFalse((self.home / ".local" / "share" / "retalk-bridge").exists())
        self.assertTrue((self.home / ".config" / "retalk-bridge" / "config.json").exists())


if __name__ == "__main__":
    unittest.main()
