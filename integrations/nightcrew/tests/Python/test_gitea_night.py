"""Unit tests for the deterministic Gitea boundary and merge policy."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from gitea_night.gitea import Gitea
from gitea_night.policy import policy_at, review_passes, run_checks
from gitea_night import agents
from gitea_night.merge import MergeController
from gitea_night.worker import in_window


def test_origin_fence_rejects_non_http_and_escaped_request():
    with pytest.raises(ValueError):
        Gitea("file:///tmp/gitea", "secret")
    client = Gitea("https://gitea.example.test", "secret")
    client.base_url = "https://github.com/api/v1"
    with pytest.raises(ValueError, match="escaped"):
        client.request("GET", "/repos")


def test_pages_continue_until_empty(monkeypatch):
    client = Gitea("https://gitea.example.test", "secret")
    batches = iter([[{"id": 1}], [{"id": 2}], []])
    monkeypatch.setattr(client, "request", lambda *args: next(batches))
    assert [item["id"] for item in client.pages("/repos")] == [1, 2]


def test_revision_marker_prevents_duplicate_comment(monkeypatch):
    client = Gitea("https://gitea.example.test", "secret")
    writes = []
    monkeypatch.setattr(client, "comments", lambda *args: [{"body": "<!-- revision:abc -->\nold"}])
    monkeypatch.setattr(client, "request", lambda *args: writes.append(args))
    assert client.comment_once("owner/repo", 1, "<!-- revision:abc -->", "new") is False
    assert writes == []


def test_review_requires_current_revisions_complete_spec_and_no_blockers():
    report = {"head": "h", "base": "b", "specification_complete": True,
        "standards": [], "specification": []}
    assert review_passes(report, "h", "b")[0]
    report["standards"] = [{"blocking": True, "status": "open"}]
    assert not review_passes(report, "h", "b")[0]
    report["standards"][0]["status"] = "dismissed"
    report['standards'][0]['verification'] = 'independent arbitration: unsupported by cited rule'
    assert review_passes(report, "h", "b")[0]
    assert not review_passes(report, "different", "b")[0]


def test_policy_comes_from_base_and_rejects_missing_checks(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.test"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    path = tmp_path / ".gitea"
    path.mkdir()
    (path / "night-merge.json").write_text(json.dumps({"version": 1, "required_checks": [["true"]]}))
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "policy"], check=True)
    base = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()
    assert policy_at(str(tmp_path), base)["required_checks"] == [["true"]]
    assert run_checks(str(tmp_path), {"required_checks": [["true"]]})[1]
    assert not run_checks(str(tmp_path), {"required_checks": [["false"]]})[1]


def test_provider_falls_back_once_with_identical_task(monkeypatch):
    calls = []
    monkeypatch.setattr(agents, "claude", lambda prompt, cwd, schema, writable:
        (_ for _ in ()).throw(agents.ProviderFailure("usage limit")))
    monkeypatch.setattr(agents, "codex", lambda prompt, cwd, schema, writable:
        calls.append((prompt, cwd, schema, writable)) or {"ok": True})
    schema = {"type": "object"}
    result, provider, failure = agents.run("same task", "/tmp", schema, True)
    assert result == {"ok": True}
    assert provider == "codex"
    assert "usage limit" in failure
    assert calls == [("same task", "/tmp", schema, True)]


@pytest.mark.parametrize("stage,hour,minute,expected", [
    ("review", 0, 29, False), ("review", 0, 30, True), ("review", 2, 59, True),
    ("review", 3, 0, False), ("resolve", 2, 59, False), ("resolve", 3, 0, True),
    ("resolve", 6, 59, True), ("resolve", 7, 0, False),
])
def test_window_boundaries(stage, hour, minute, expected):
    now = __import__("datetime").datetime(2026, 9, 8, hour, minute,
        tzinfo=__import__("zoneinfo").ZoneInfo("America/Toronto"))
    assert in_window(stage, now) is expected


class FakeGitea:
    def __init__(self, pull, mirrors=None):
        self.current = pull
        self.mirrors = mirrors or []
        self.writes = []

    def pull(self, repo, number):
        return self.current

    def push_mirrors(self, repo):
        return self.mirrors

    def outbound_writes(self, repo):
        return self.mirrors

    def request(self, method, path, body=None):
        self.writes.append((method, path, body))
        if "/branches/" in path:
            return {"commit": {"id": self.current["base"]["sha"]}}
        return {}

    def create_issue_once(self, *args):
        self.writes.append(("incident", args, None))


@pytest.mark.parametrize("change", ["draft", "hold", "conflict", "mirror"])
def test_merge_rejects_nonmergeable_states(monkeypatch, tmp_path, change):
    pull = {"state": "open", "draft": False, "mergeable": True, "labels": [],
        "head": {"sha": "h"}, "base": {"sha": "b", "ref": "main"}}
    mirrors = []
    if change == "draft":
        pull["draft"] = True
    if change == "hold":
        pull["labels"] = [{"name": "night:hold"}]
    if change == "conflict":
        pull["mergeable"] = False
    if change == "mirror":
        mirrors = [{}]
    gitea = FakeGitea(pull, mirrors)
    report = {"head": "h", "base": "b", "specification_complete": True,
        "standards": [], "specification": []}
    with pytest.raises(ValueError):
        MergeController(gitea, tmp_path).merge("owner/repo", 1, str(tmp_path), report)
    assert not any(write[0] == "POST" and write[1].endswith("/merge") for write in gitea.writes)


def test_merge_rejects_stale_review_before_validation(tmp_path):
    pull = {"state": "open", "draft": False, "mergeable": True, "labels": [],
        "head": {"sha": "new-head"}, "base": {"sha": "base", "ref": "main"}}
    gitea = FakeGitea(pull)
    stale = {"head": "old-head", "base": "base", "specification_complete": True,
        "standards": [], "specification": []}
    with pytest.raises(ValueError, match="stale"):
        MergeController(gitea, tmp_path).merge("owner/repo", 1, str(tmp_path), stale)


def test_integration_checkout_contains_current_base_and_head(tmp_path):
    repo = tmp_path / "repo"
    state = tmp_path / "state"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "common.txt").write_text("common")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "common"], check=True)
    common = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    subprocess.run(["git", "-C", str(repo), "checkout", "-qb", "feature"], check=True)
    (repo / "head.txt").write_text("head")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "head"], check=True)
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "master"], check=True)
    (repo / "base.txt").write_text("base")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    integration, _ = MergeController(FakeGitea({}), state)._integration(str(repo), base, head, "pre")

    assert (Path(integration) / "base.txt").read_text() == "base"
    assert (Path(integration) / "head.txt").read_text() == "head"
    assert common


@pytest.mark.parametrize('state', [None, 'pending', 'failure', 'error', 'skipped', 'cancelled'])
def test_required_statuses_fail_closed(tmp_path, state):
    api = FakeGitea({})
    api.request = lambda *args: {'status_check_contexts': ['ci/test']}
    api.pages = lambda *args: [] if state is None else [{'id': 1, 'context': 'ci/test', 'status': state}]
    with pytest.raises(ValueError, match='status missing'):
        MergeController(api, tmp_path).required_statuses('owner/repo', 'main', 'head', {})


def test_latest_required_status_wins(tmp_path):
    api = FakeGitea({})
    api.request = lambda *args: {'status_check_contexts': ['ci/test']}
    api.pages = lambda *args: [
        {'id': 1, 'context': 'ci/test', 'status': 'failure'},
        {'id': 2, 'context': 'ci/test', 'status': 'success'}]
    MergeController(api, tmp_path).required_statuses('owner/repo', 'main', 'head', {})


def test_missing_axis_or_unverified_dismissal_cannot_pass():
    report = {'head': 'h', 'base': 'b', 'specification_complete': True}
    assert not review_passes(report, 'h', 'b')[0]
    report.update(standards=[{'blocking': True, 'status': 'dismissed'}], specification=[])
    assert not review_passes(report, 'h', 'b')[0]


@pytest.mark.parametrize('url', ['https://github.com', 'https://api.github.com', 'https://uploads.github.com'])
def test_github_cannot_be_configured_as_mutation_target(url):
    with pytest.raises(ValueError, match='GitHub'):
        Gitea(url, 'unused')


def test_window_is_rechecked_after_discovery(monkeypatch, tmp_path):
    from gitea_night import worker as module
    windows = iter([True, False])
    monkeypatch.setattr(module, 'in_window', lambda stage: next(windows))
    worker = module.NightWorker(FakeGitea({}), object(), tmp_path, 'owner')
    monkeypatch.setattr(worker, 'discover', lambda: {})
    assert worker.run_one('review')['reason'] == 'window ended during discovery'
