"""Outside-in tests for skills/pr-review-resolve-loop/scripts/gitea_merge.py.

Contract: checks one PR against a clean review receipt kept in local
controller state (~/.local/state/gitea-pr-review-resolve) and, only with
--execute, asks Gitea to merge exactly the reviewed head once. Stdout is one
JSON object; a refusal is {"status": "blocked", "reason": ...} with exit 1.
Successful results are also appended to merges.jsonl in the state folder.
"""

import fcntl
import json
import os
import unittest

from support import FakeServer, HelperTestCase, base_env, deepcopy, run_tool

HEAD = "1" * 40
BASE = "2" * 40
MERGED = "3" * 40
PR_PATH = "/api/v1/repos/o/r/pulls/5"


def open_pr():
    return {"number": 5, "state": "open", "merged": False, "draft": False, "mergeable": True,
            "head": {"sha": HEAD, "ref": "feat/x", "repo": {"full_name": "o/r"}},
            "base": {"sha": BASE, "ref": "develop"},
            "labels": [{"name": "review:clear"}, {"name": "kind:feature"}],
            "merge_commit_sha": None}


class FakeGitea:
    """PR, status and merge endpoints with scripted behavior."""

    def __init__(self):
        self.pr = open_pr()
        self.statuses = [{"id": 1, "context": "ci/check", "status": "success"}]
        self.status_pages = None
        self.pr_after = {}
        self.merge_reply = (200, "")
        self.merge_takes_effect = True
        self.pr_gets = 0

    def __call__(self, request):
        if request.path == PR_PATH and request.method == "GET":
            self.pr_gets += 1
            if self.pr_gets in self.pr_after:
                self.pr = self.pr_after[self.pr_gets](deepcopy(self.pr))
            return 200, self.pr
        if request.path == f"/api/v1/repos/o/r/commits/{HEAD}/statuses" and request.method == "GET":
            page = int(request.query["page"][0])
            pages = self.status_pages or [self.statuses]
            return 200, pages[page - 1] if page <= len(pages) else []
        if request.path == PR_PATH + "/merge" and request.method == "POST":
            if self.merge_takes_effect:
                self.pr = dict(self.pr, merged=True, state="closed", merge_commit_sha=MERGED)
            return self.merge_reply
        return 404, {"message": "not found"}


class GiteaMergeTest(HelperTestCase):
    def setUp(self):
        super().setUp()
        self.gitea = FakeGitea()
        self.server = FakeServer(self.gitea).__enter__()
        self.addCleanup(self.server.__exit__, None, None, None)
        self.state = self.home / ".local" / "state" / "gitea-pr-review-resolve"
        self.receipt = {"schema_version": 1, "server": self.server.url, "repo": "o/r", "pr": 5,
                        "head_sha": HEAD, "base_sha": BASE, "base_ref": "develop", "head_ref": "feat/x",
                        "head_repo": "o/r", "findings": [], "standards_review": "clear", "spec_review": "clear",
                        "required_contexts": ["ci/check"]}
        self.env_extra = {"GITEA_SERVER_URL": self.server.url + "/", "GITEA_TOKEN": "merge-token"}

    def receipt_path(self):
        path = self.state / "o-r" / "5" / "receipt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        for folder in [self.state, self.state / "o-r", path.parent]:
            folder.chmod(0o700)
        path.write_text(json.dumps(self.receipt))
        path.chmod(0o600)
        return path

    def merge(self, *extra, receipt=None, method="squash", env=None):
        receipt = receipt or self.receipt_path()
        values = dict(self.env_extra)
        values.update(env or {})
        values = {k: v for k, v in values.items() if v is not None}
        return run_tool("gitea_merge", ["--repo", "o/r", "--pr", "5", "--receipt", receipt, "--method", method, *extra],
                        env=base_env(self.home, values))

    def assert_blocked(self, result, reason_part):
        self.assertEqual(result.returncode, 1, result.stdout)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "blocked")
        self.assertIn(reason_part, output["reason"])
        self.assertEqual(self.server.matching("POST"), [])
        return output

    def log_lines(self):
        path = self.state / "merges.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    # Read-only checks

    def test_eligible_dry_run_never_merges(self):
        result = self.merge()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {"status": "eligible", "head": HEAD, "mutation": False})
        self.assertEqual(self.server.matching("POST"), [])
        self.assertEqual(self.log_lines(), [{"repo": "o/r", "pr": 5, "status": "eligible", "head": HEAD, "mutation": False}])
        self.assertTrue(all(r.headers["authorization"] == "token merge-token" for r in self.server.requests))

    def test_stale_head_or_base(self):
        for field in ("head_sha", "base_sha"):
            with self.subTest(field=field):
                original = self.receipt[field]
                self.receipt[field] = "9" * 40
                self.assert_blocked(self.merge(), "Review is stale")
                self.receipt[field] = original

    def test_branch_identity_changed(self):
        for field, value in (("base_ref", "main"), ("head_ref", "feat/y"), ("head_repo", "fork/r")):
            with self.subTest(field=field):
                original = self.receipt[field]
                self.receipt[field] = value
                self.assert_blocked(self.merge(), "branch identity changed")
                self.receipt[field] = original

    def test_receipt_identity_mismatch(self):
        for field, value in (("server", "http://elsewhere"), ("repo", "o/other"), ("pr", 6), ("pr", "5")):
            with self.subTest(field=field, value=value):
                original = self.receipt[field]
                self.receipt[field] = value
                self.assert_blocked(self.merge(), "identity mismatch")
                self.receipt[field] = original

    def test_pr_must_be_open_unmerged_non_draft_and_mergeable(self):
        cases = [({"state": "closed"}, "open, unmerged and non-draft"), ({"merged": True}, "open, unmerged and non-draft"),
                 ({"draft": True}, "open, unmerged and non-draft"), ({"draft": None}, "open, unmerged and non-draft"),
                 ({"mergeable": False}, "mergeability"), ({"mergeable": None}, "mergeability")]
        for change, reason in cases:
            with self.subTest(change=change):
                self.gitea.pr = dict(open_pr(), **change)
                self.assert_blocked(self.merge(), reason)

    def test_labels(self):
        for labels in ([], ["kind:feature"], ["review:clear", "review:findings"], ["review:clear", "review:needs-human"],
                       ["review:clear", "review:requested"], ["review:clear", "review:in-progress"],
                       ["review:clear", "review:resolving"]):
            with self.subTest(labels=labels):
                self.gitea.pr = dict(open_pr(), labels=[{"name": n} for n in labels])
                self.assert_blocked(self.merge(), "review:clear")

    def test_receipt_contents(self):
        cases = [({"schema_version": 2}, "version 1"), ({"findings": [{"id": 1}]}, "version 1"), ({"findings": None}, "version 1"),
                 ({"standards_review": "findings"}, "axes"), ({"spec_review": None}, "axes"),
                 ({"required_contexts": []}, "required validation contexts"),
                 ({"required_contexts": "ci/check"}, "required validation contexts"),
                 ({"required_contexts": [""]}, "required validation contexts")]
        for change, reason in cases:
            with self.subTest(change=change):
                saved = deepcopy(self.receipt)
                self.receipt.update(change)
                self.assert_blocked(self.merge(), reason)
                self.receipt = saved

    def test_required_context_missing_pending_or_failed(self):
        for statuses in ([], [{"id": 1, "context": "ci/check", "status": "pending"}],
                         [{"id": 1, "context": "ci/check", "status": "failure"}],
                         [{"id": 1, "context": "other", "status": "success"}]):
            with self.subTest(statuses=statuses):
                self.gitea.statuses = statuses
                self.assert_blocked(self.merge(), "Required current-head validation")

    def test_any_other_published_status_must_be_green(self):
        self.gitea.statuses = [{"id": 1, "context": "ci/check", "status": "success"},
                               {"id": 2, "context": "ci/extra", "status": "pending"}]
        self.assert_blocked(self.merge(), "pending or failing")

    def test_latest_status_per_context_wins(self):
        self.gitea.statuses = [{"id": 3, "context": "ci/check", "status": "success"},
                               {"id": 1, "context": "ci/check", "status": "failure"},
                               {"id": 2, "context": "ci/extra", "status": "error"},
                               {"id": 4, "context": "ci/extra", "status": "success"}]
        result = self.merge()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.gitea.statuses = [{"id": 1, "context": "ci/check", "status": "success"},
                               {"id": 2, "context": "ci/check", "status": "failure"}]
        self.assert_blocked(self.merge(), "Required current-head validation")

    def test_statuses_are_read_across_pages(self):
        filler = [{"id": n, "context": f"c{n}", "status": "success"} for n in range(1, 51)]
        self.gitea.status_pages = [filler, [{"id": 60, "context": "ci/check", "status": "success"},
                                            {"id": 61, "context": "late", "status": "failure"}]]
        self.assert_blocked(self.merge(), "pending or failing")
        pages = [r.query["page"][0] for r in self.server.requests if "/statuses" in r.path]
        self.assertEqual(pages, ["1", "2", "3"])
        self.assertTrue(all(r.query["limit"] == ["50"] for r in self.server.requests if "/statuses" in r.path))

    # Local state and configuration

    def test_receipt_must_live_in_controller_state(self):
        outside = self.tmp / "checkout" / "receipt.json"
        outside.parent.mkdir()
        outside.write_text(json.dumps(self.receipt))
        outside.chmod(0o600)
        self.assert_blocked(self.merge(receipt=outside), "local controller state")
        self.assertEqual(self.server.requests, [])

    def test_receipt_and_state_must_not_be_writable_by_others(self):
        for target, mode in (("receipt", 0o620), ("receipt", 0o602), ("folder", 0o770), ("state", 0o707)):
            with self.subTest(target=target, mode=mode):
                path = self.receipt_path()
                {"receipt": path, "folder": path.parent, "state": self.state}[target].chmod(mode)
                self.assert_blocked(self.merge(receipt=path), "not writable by others")
        self.assertEqual(self.server.requests, [])

    def test_state_folder_is_created_privately(self):
        outside = self.tmp / "r.json"
        outside.write_text("{}")
        self.merge(receipt=outside)
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o700)

    def test_missing_token_and_server(self):
        self.assert_blocked(self.merge(env={"GITEA_TOKEN": None, "GITEA_TOKEN_FILE": str(self.tmp / "absent")}),
                            "Gitea token missing")
        self.assert_blocked(self.merge(env={"GITEA_SERVER_URL": None}), "Set GITEA_SERVER_URL")
        self.assertEqual(self.server.requests, [])

    def test_token_file(self):
        token = self.tmp / "token"
        token.write_text("file-token\n")
        result = self.merge(env={"GITEA_TOKEN": None, "GITEA_TOKEN_FILE": str(token)})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.server.requests[0].headers["authorization"], "token file-token")

    def test_invalid_repository(self):
        path = self.receipt_path()
        result = run_tool("gitea_merge", ["--repo", "o/r/x", "--pr", "5", "--receipt", path, "--method", "merge"],
                          env=base_env(self.home, self.env_extra))
        self.assert_blocked(result, "Invalid repository or PR number")
        result = run_tool("gitea_merge", ["--repo", "o/r", "--pr", "0", "--receipt", path, "--method", "merge"],
                          env=base_env(self.home, self.env_extra))
        self.assert_blocked(result, "Invalid repository or PR number")

    def test_invalid_method_is_a_usage_error(self):
        result = self.merge(method="octopus")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.server.requests, [])

    def test_http_error_and_redirect(self):
        server_handler = self.server.handler

        def not_found(request):
            return 404, {"message": "missing"}
        self.server.handler = not_found
        self.assert_blocked(self.merge(), "Gitea HTTP 404")

        def redirect(request):
            return 302, "", {"Location": "http://127.0.0.1:9/elsewhere"}
        self.server.handler = redirect
        self.assert_blocked(self.merge(), "redirect refused")
        self.server.handler = server_handler

    def test_held_lock_blocks(self):
        path = self.receipt_path()
        with (self.state / "merge.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.assert_blocked(self.merge(receipt=path), "Another merge controller owns the lock")
        self.assertEqual(self.server.requests, [])

    # Execute mode

    def test_execute_merges_exactly_the_reviewed_head(self):
        result = self.merge("--execute", method="rebase")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout), {"status": "merged", "head": HEAD, "merge_commit": MERGED})
        posts = self.server.matching("POST")
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].path, PR_PATH + "/merge")
        self.assertEqual(posts[0].json(), {"do": "rebase", "head_commit_id": HEAD, "force_merge": False,
                                           "delete_branch_after_merge": False, "merge_when_checks_succeed": False})
        self.assertEqual(self.gitea.pr_gets, 3)
        self.assertEqual(self.log_lines(), [{"repo": "o/r", "pr": 5, "status": "merged", "head": HEAD, "merge_commit": MERGED}])

    def test_execute_rechecks_before_merging(self):
        self.gitea.pr_after = {2: lambda pr: dict(pr, labels=[{"name": "review:clear"}, {"name": "review:requested"}])}
        self.assert_blocked(self.merge("--execute"), "review:clear")
        self.gitea.pr_gets = 0
        self.gitea.pr = open_pr()
        self.gitea.pr_after = {2: lambda pr: dict(pr, head=dict(pr["head"], sha="4" * 40))}
        self.assert_blocked(self.merge("--execute"), "Review is stale")
        self.assertEqual(self.log_lines(), [])

    def test_failed_merge_request_is_inspected_once_and_never_retried(self):
        self.gitea.merge_reply = (500, {"message": "boom"})
        self.gitea.merge_takes_effect = False
        result = self.merge("--execute")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Merge revision not verified", json.loads(result.stdout)["reason"])
        self.assertEqual(len(self.server.matching("POST")), 1)
        self.assertEqual(self.gitea.pr_gets, 3)

    def test_merge_accepted_despite_error_reply_is_reported_as_merged(self):
        self.gitea.merge_reply = (504, "gateway timeout")
        result = self.merge("--execute")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["merge_commit"], MERGED)
        self.assertEqual(len(self.server.matching("POST")), 1)

    def test_unverifiable_merge_commit(self):
        for sha in (None, "abc", "A" * 40, "a" * 41):
            with self.subTest(sha=sha):
                self.gitea.pr = open_pr()
                self.gitea.pr_gets = 0
                self.gitea.pr_after = {3: lambda pr, sha=sha: dict(pr, merge_commit_sha=sha)}
                result = self.merge("--execute")
                self.assertEqual(result.returncode, 1)
                self.assertIn("Merge revision not verified", json.loads(result.stdout)["reason"])


if __name__ == "__main__":
    unittest.main()
