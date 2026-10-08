"""Outside-in tests for scripts/parity.py.

Contract: four JSON report files (oracle run 1, oracle run 2, port run 1, port
run 2). Exit 0 with one PASS line when every scenario passed with observations,
each lane is deterministic and the lanes agree; otherwise exit 1 with a
one-line reason on stderr.
"""

import json
import unittest

from support import HelperTestCase, base_env, run_tool

GOOD = {"login": {"status": "passed", "observations": {"code": 200, "body": ["a", "b"]}},
        "logout": {"status": "passed", "observations": []}}


class ParityTest(HelperTestCase):
    def run_reports(self, *reports, raw=None):
        paths = []
        for index, report in enumerate(reports):
            path = self.tmp / f"report{index}.json"
            path.write_text(raw[index] if raw and raw[index] is not None else json.dumps(report))
            paths.append(path)
        return run_tool("parity", paths, env=base_env(self.home))

    def assert_fails(self, result, message):
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, message + "\n")

    def test_pass(self):
        result = self.run_reports(GOOD, GOOD, GOOD, GOOD)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "PASS: 2 scenarios, both lanes green and deterministic\n")

    def test_key_order_and_whitespace_do_not_matter(self):
        reordered = '{"logout": {"observations": [], "status": "passed"},\n "login": {"observations": {"body": ["a","b"], "code": 200}, "status": "passed"}}'
        result = self.run_reports(GOOD, GOOD, GOOD, GOOD, raw=[None, None, reordered, None])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_red_or_skipped_scenario(self):
        for outcome in [{"status": "failed", "observations": 1}, {"status": "skipped", "observations": 1},
                        {"status": "passed"}, "passed"]:
            with self.subTest(outcome=outcome):
                bad = dict(GOOD, logout=outcome)
                result = self.run_reports(GOOD, GOOD, bad, bad)
                self.assert_fails(result, "Scenario logout is missing, red, skipped, or lacks observations")

    def test_empty_or_non_object_report(self):
        for report in [{}, [], "x"]:
            with self.subTest(report=report):
                self.assert_fails(self.run_reports(GOOD, report, GOOD, GOOD), "Each report must contain scenarios")

    def test_nondeterministic_lane(self):
        changed = dict(GOOD, login={"status": "passed", "observations": {"code": 201, "body": ["a", "b"]}})
        self.assert_fails(self.run_reports(GOOD, changed, GOOD, GOOD), "Nondeterministic lane: repeated runs differ")
        self.assert_fails(self.run_reports(GOOD, GOOD, GOOD, changed), "Nondeterministic lane: repeated runs differ")

    def test_lanes_disagree(self):
        changed = dict(GOOD, login={"status": "passed", "observations": {"code": 201, "body": ["a", "b"]}})
        self.assert_fails(self.run_reports(GOOD, GOOD, changed, changed),
                          "Behavior parity mismatch (including missing or extra scenarios)")

    def test_extra_scenario_is_a_mismatch(self):
        extra = dict(GOOD, signup={"status": "passed", "observations": None})
        self.assert_fails(self.run_reports(GOOD, GOOD, extra, extra),
                          "Behavior parity mismatch (including missing or extra scenarios)")

    def test_json_types_are_compared_exactly(self):
        as_int = {"s": {"status": "passed", "observations": 1}}
        as_bool = {"s": {"status": "passed", "observations": True}}
        as_float = {"s": {"status": "passed", "observations": 1.0}}
        for other in (as_bool, as_float):
            with self.subTest(other=other):
                self.assert_fails(self.run_reports(as_int, as_int, other, other),
                                  "Behavior parity mismatch (including missing or extra scenarios)")

    def test_missing_file(self):
        paths = [self.tmp / "absent.json"] + [self.write_json(f"r{i}.json", GOOD) for i in range(3)]
        result = run_tool("parity", paths, env=base_env(self.home))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.strip())

    def test_wrong_number_of_reports_is_a_usage_error(self):
        paths = [self.write_json(f"r{i}.json", GOOD) for i in range(3)]
        result = run_tool("parity", paths, env=base_env(self.home))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
