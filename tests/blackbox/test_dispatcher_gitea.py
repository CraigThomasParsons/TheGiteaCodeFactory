"""Outside-in tests for skills/dispatcher/scripts/gitea.py, against a fake Gitea.

Contract: `list --repo OWNER/NAME [--state all|open|closed]` prints every issue
across pages as a JSON array; `request METHOD PATH [--body-file F]` calls one
allow-listed issue/PR route and prints the JSON reply. Configuration comes
from GITEA_SERVER_URL plus GITEA_TOKEN or GITEA_TOKEN_FILE (default
~/.config/gitea-code-factory/token). Failures exit 1 with a message on stderr.
"""

import json
import unittest

from support import FakeServer, HelperTestCase, base_env, run_tool


def issues_handler(total):
    issues = [{"number": n, "title": f"Issue {n}"} for n in range(1, total + 1)]

    def handle(request):
        if request.method == "GET" and request.path == "/api/v1/repos/o/r/issues":
            page = int(request.query["page"][0])
            limit = int(request.query["limit"][0])
            return 200, issues[(page - 1) * limit: page * limit]
        return 404, {"message": "not found"}
    return handle


class DispatcherGiteaTest(HelperTestCase):
    def env(self, server, **extra):
        values = {"GITEA_SERVER_URL": server.url + "/", "GITEA_TOKEN": "test-token"}
        values.update(extra)
        return base_env(self.home, {k: v for k, v in values.items() if v is not None})

    def test_list_follows_pages_until_empty(self):
        with FakeServer(issues_handler(120)) as server:
            result = run_tool("dispatcher_gitea", ["list", "--repo", "o/r"], env=self.env(server))
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)
        self.assertEqual([row["number"] for row in rows], list(range(1, 121)))
        pages = [r.query for r in server.requests]
        self.assertEqual([p["page"] for p in pages], [["1"], ["2"], ["3"], ["4"]])
        self.assertTrue(all(p["state"] == ["all"] and p["limit"] == ["50"] for p in pages))
        self.assertTrue(all(r.headers["authorization"] == "token test-token" for r in server.requests))

    def test_list_state_filter_and_empty_repo(self):
        with FakeServer(issues_handler(0)) as server:
            result = run_tool("dispatcher_gitea", ["list", "--repo", "o/r", "--state", "open"], env=self.env(server))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])
        self.assertEqual(server.requests[0].query["state"], ["open"])

    def test_list_rejects_bad_state_and_repo(self):
        with FakeServer(issues_handler(1)) as server:
            bad_state = run_tool("dispatcher_gitea", ["list", "--repo", "o/r", "--state", "merged"], env=self.env(server))
            bad_repo = run_tool("dispatcher_gitea", ["list", "--repo", "o/r/x"], env=self.env(server))
        self.assertNotEqual(bad_state.returncode, 0)
        self.assertEqual(bad_repo.returncode, 1)
        self.assertEqual(bad_repo.stderr, "Invalid repo\n")
        self.assertEqual(server.requests, [])

    def test_list_rejects_non_list_reply(self):
        with FakeServer(lambda r: (200, {"message": "odd"})) as server:
            result = run_tool("dispatcher_gitea", ["list", "--repo", "o/r"], env=self.env(server))
        self.assertEqual((result.returncode, result.stderr), (1, "Expected issue list\n"))

    def test_request_get(self):
        def handle(request):
            return 200, {"number": 7, "path": request.path}
        with FakeServer(handle) as server:
            result = run_tool("dispatcher_gitea", ["request", "GET", "/repos/o/r.js/pulls/7"], env=self.env(server))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"number": 7, "path": "/api/v1/repos/o/r.js/pulls/7"})
        self.assertEqual(server.requests[0].body, "")

    def test_request_post_and_patch_send_the_body_file(self):
        body = self.write_json("body.json", {"body": "Looks good", "nested": {"a": [1, 2]}})
        with FakeServer(lambda r: (201, {"id": 1})) as server:
            post = run_tool("dispatcher_gitea", ["request", "POST", "/repos/o/r/issues/3/comments", "--body-file", body],
                            env=self.env(server))
            patch = run_tool("dispatcher_gitea", ["request", "PATCH", "/repos/o/r/issues/3", "--body-file", body],
                             env=self.env(server))
        self.assertEqual(post.returncode, 0, post.stderr)
        self.assertEqual(patch.returncode, 0, patch.stderr)
        self.assertEqual(json.loads(post.stdout), {"id": 1})
        self.assertEqual([(r.method, r.path) for r in server.requests],
                         [("POST", "/api/v1/repos/o/r/issues/3/comments"), ("PATCH", "/api/v1/repos/o/r/issues/3")])
        for request in server.requests:
            self.assertEqual(request.json(), {"body": "Looks good", "nested": {"a": [1, 2]}})
            self.assertEqual(request.headers["content-type"], "application/json")

    def test_allowed_routes(self):
        routes = ["/repos/o/r/issues", "/repos/o/r/pulls", "/repos/o/r/issues/1/comments",
                  "/repos/o/r/pulls/2/reviews", "/repos/o/r/pulls/2/commits", "/repos/o/r/issues/comments"]
        with FakeServer(lambda r: (200, [])) as server:
            for route in routes:
                with self.subTest(route=route):
                    result = run_tool("dispatcher_gitea", ["request", "GET", route], env=self.env(server))
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_disallowed_routes_never_reach_the_server(self):
        routes = ["/repos/o/r/pulls/2/merge", "/repos/o/r", "/user", "/repos/o/r/issues/1/labels",
                  "/repos/o/r/issues?state=open", "/repos/o/../r/issues", "repos/o/r/issues"]
        with FakeServer(lambda r: (200, {})) as server:
            for route in routes:
                with self.subTest(route=route):
                    result = run_tool("dispatcher_gitea", ["request", "GET", route], env=self.env(server))
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stderr, "Unsupported route; use repository issue/PR metadata routes only\n")
        self.assertEqual(server.requests, [])

    def test_disallowed_methods(self):
        with FakeServer(lambda r: (200, {})) as server:
            for method in ["DELETE", "PUT", "get"]:
                with self.subTest(method=method):
                    result = run_tool("dispatcher_gitea", ["request", method, "/repos/o/r/issues"], env=self.env(server))
                    self.assertNotEqual(result.returncode, 0)
        self.assertEqual(server.requests, [])

    def test_http_error(self):
        with FakeServer(lambda r: (404, {"message": "not found"})) as server:
            result = run_tool("dispatcher_gitea", ["request", "GET", "/repos/o/r/issues/9"], env=self.env(server))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "Gitea HTTP 404; request not completed\n")

    def test_token_file_and_default_token_location(self):
        token_file = self.tmp / "token"
        token_file.write_text("  from-file \n")
        default = self.home / ".config" / "gitea-code-factory" / "token"
        default.parent.mkdir(parents=True)
        default.write_text("from-default\n")
        with FakeServer(lambda r: (200, [])) as server:
            run_tool("dispatcher_gitea", ["request", "GET", "/repos/o/r/issues"],
                     env=self.env(server, GITEA_TOKEN=None, GITEA_TOKEN_FILE=str(token_file)))
            run_tool("dispatcher_gitea", ["request", "GET", "/repos/o/r/issues"], env=self.env(server, GITEA_TOKEN=None))
            run_tool("dispatcher_gitea", ["request", "GET", "/repos/o/r/issues"],
                     env=self.env(server, GITEA_TOKEN="  ", GITEA_TOKEN_FILE=str(token_file)))
        self.assertEqual([r.headers["authorization"] for r in server.requests],
                         ["token from-file", "token from-default", "token from-file"])

    def test_missing_token(self):
        with FakeServer(lambda r: (200, [])) as server:
            result = run_tool("dispatcher_gitea", ["request", "GET", "/repos/o/r/issues"],
                              env=self.env(server, GITEA_TOKEN=None, GITEA_TOKEN_FILE=str(self.tmp / "absent")))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "Gitea token missing from GITEA_TOKEN or GITEA_TOKEN_FILE\n")
        self.assertEqual(server.requests, [])

    def test_missing_server(self):
        env = base_env(self.home, {"GITEA_TOKEN": "t"})
        for args in (["request", "GET", "/repos/o/r/issues"], ["list", "--repo", "o/r"]):
            with self.subTest(args=args):
                result = run_tool("dispatcher_gitea", args, env=env)
                self.assertEqual((result.returncode, result.stderr), (1, "Set GITEA_SERVER_URL\n"))

    def test_subcommand_required(self):
        result = run_tool("dispatcher_gitea", [], env=base_env(self.home))
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
