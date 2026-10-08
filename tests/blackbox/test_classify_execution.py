"""Outside-in tests for skills/supervise-agent-pipeline/scripts/classify_execution.py.

Contract: one JSON object on stdin; on success stdout is {"state": NAME} and
the exit code is 0; on bad input stderr is {"error": MESSAGE} and the exit
code is 2.
"""

import json
import unittest

from support import HelperTestCase, base_env, run_tool


class ClassifyExecutionTest(HelperTestCase):
    def classify(self, observation):
        text = observation if isinstance(observation, str) else json.dumps(observation)
        return run_tool("classify", [], env=base_env(self.home), stdin=text)

    def assert_state(self, observation, state):
        result = self.classify(observation)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"state": state})
        self.assertEqual(result.stderr, "")

    def test_each_state(self):
        cases = [
            ({"scopeViolation": True}, "BLOCKED_SCOPE"),
            ({"gateFailure": True}, "BLOCKED_GATE"),
            ({"approvalRequired": True}, "WAITING_APPROVAL"),
            ({"providerFailure": True}, "WAITING_PROVIDER"),
            ({"working": True}, "WORKING"),
            ({"subagentsWorking": True}, "WORKING"),
            ({"receiptValid": True, "evidenceSatisfied": True}, "DONE"),
            ({"processAlive": False}, "FAILED_INFRASTRUCTURE"),
            ({"idleStreak": 2}, "STALLED"),
            ({"idleStreak": 5}, "STALLED"),
            ({"idleStreak": 1}, "IDLE"),
            ({}, "IDLE"),
        ]
        for observation, state in cases:
            with self.subTest(observation=observation):
                self.assert_state(observation, state)

    def test_precedence_is_fail_closed(self):
        everything = {"scopeViolation": True, "gateFailure": True, "approvalRequired": True,
                      "providerFailure": True, "working": True, "receiptValid": True,
                      "evidenceSatisfied": True, "processAlive": False, "idleStreak": 9}
        order = ["scopeViolation", "gateFailure", "approvalRequired", "providerFailure", "working"]
        expected = ["BLOCKED_SCOPE", "BLOCKED_GATE", "WAITING_APPROVAL", "WAITING_PROVIDER", "WORKING"]
        observation = dict(everything)
        for key, state in zip(order, expected):
            with self.subTest(remaining=sorted(observation)):
                self.assert_state(observation, state)
            observation.pop(key)
        self.assert_state(observation, "DONE")
        observation.pop("receiptValid")
        self.assert_state(observation, "FAILED_INFRASTRUCTURE")
        observation.pop("processAlive")
        self.assert_state(observation, "STALLED")

    def test_receipt_alone_is_not_done(self):
        self.assert_state({"receiptValid": True}, "IDLE")
        self.assert_state({"evidenceSatisfied": True, "idleStreak": 3}, "STALLED")

    def test_truthiness_of_flags(self):
        self.assert_state({"scopeViolation": 1}, "BLOCKED_SCOPE")
        self.assert_state({"scopeViolation": 0, "working": "yes"}, "WORKING")
        self.assert_state({"processAlive": 0}, "FAILED_INFRASTRUCTURE")
        self.assert_state({"processAlive": None}, "FAILED_INFRASTRUCTURE")

    def test_invalid_input_exits_2_with_json_error(self):
        for text in ["", "not json", "[1, 2]", "42", json.dumps({"idleStreak": -1}),
                     json.dumps({"idleStreak": "3"}), json.dumps({"idleStreak": 1.5})]:
            with self.subTest(stdin=text):
                result = self.classify(text)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("error", json.loads(result.stderr))

    def test_invalid_idle_streak_ignored_when_an_earlier_rule_applies(self):
        self.assert_state({"working": True, "idleStreak": -1}, "WORKING")


if __name__ == "__main__":
    unittest.main()
