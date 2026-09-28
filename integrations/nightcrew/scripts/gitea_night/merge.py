"""Deterministic, serialized Gitea merge controller."""
from __future__ import annotations

import fcntl
import hashlib
import json
import urllib.parse
import urllib.error
from pathlib import Path

from .policy import git, policy_at, review_passes, run_checks


class MergeController:
    """Re-fetch and prove every gate before submitting a guarded merge."""

    def __init__(self, gitea, state_dir: Path):
        self.gitea = gitea
        self.state_dir = state_dir

    def _paths(self, repo: str, target: str):
        key = hashlib.sha256(f"{repo}:{target}".encode()).hexdigest()
        root = self.state_dir / "targets"
        root.mkdir(parents=True, exist_ok=True)
        return root / (key + ".lock"), root / (key + ".json")

    def _integration(self, checkout: str, base: str, head: str, label: str):
        """Materialize an immutable synthetic merge or actual merged revision."""
        if label == "pre":
            tree = git(checkout, "merge-tree", "--write-tree", base, head).stdout.splitlines()[0]
            commit = git(checkout, "-c", "user.name=TheNightCrew",
                "-c", "user.email=nightcrew@localhost", "commit-tree", tree,
                "-p", base, "-p", head, "-m", "validated integration").stdout.strip()
        else:
            commit = head
            tree = git(checkout, "rev-parse", commit + "^{tree}").stdout.strip()
        key = hashlib.sha256(f"{base}:{head}:{label}".encode()).hexdigest()
        path = self.state_dir / "integrations" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            git(checkout, "worktree", "add", "--detach", str(path), commit)
        return str(path), tree

    def merge(self, repo: str, number: int, checkout: str, report: dict):
        """Merge only a current, validated, unheld PR; retain its branch."""
        initial = self.gitea.pull(repo, number)
        target = initial["base"]["ref"]
        lock_path, pause_path = self._paths(repo, target)
        with lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if pause_path.exists():
                raise ValueError("target is paused")
            if self.gitea.outbound_writes(repo):
                raise ValueError("outbound integration holds repository")
            pull = self.gitea.pull(repo, number)
            held = any(label["name"] in ("night:hold", "night:blocked") for label in pull.get("labels", []))
            if pull.get("state") != "open" or pull.get("draft") or not pull.get("mergeable") or held:
                raise ValueError("pull request is not mergeable")
            head, base = pull["head"]["sha"], pull["base"]["sha"]
            passed, reason = review_passes(report, head, base)
            if not passed:
                raise ValueError(reason)
            policy = policy_at(checkout, base)
            changes = git(checkout, 'diff', '--name-only', base + '...' + head).stdout.splitlines()
            if '.gitea/night-merge.json' in changes:
                raise ValueError('gate-definition changes require separate approval')
            integration, expected_tree = self._integration(checkout, base, head, "pre")
            evidence, checks_passed = run_checks(integration, policy)
            if not checks_passed:
                raise ValueError("required validation failed")
            fresh = self.gitea.pull(repo, number)
            if (fresh["head"]["sha"], fresh["base"]["sha"]) != (head, base):
                raise ValueError("pull request changed during validation")
            if (fresh.get('state') != 'open' or fresh.get('draft') or not fresh.get('mergeable')
                    or any(label['name'] in ('night:hold', 'night:blocked') for label in fresh.get('labels', []))):
                raise ValueError('PR eligibility changed during validation')
            self.required_statuses(repo, target, head, policy)
            branch = self.gitea.request("GET", f"/repos/{repo}/branches/{urllib.parse.quote(target, safe='')}")
            if branch["commit"]["id"] != base:
                raise ValueError("target moved during validation")
            try:
                self.gitea.request("POST", f"/repos/{repo}/pulls/{number}/merge", {
                    "do": policy.get("merge_strategy", "merge"), "head_commit_id": head,
                    "force_merge": False, "delete_branch_after_merge": False})
                merged = self.gitea.pull(repo, number)
                if not merged.get("merged") or not merged.get("merge_commit_sha"):
                    raise RuntimeError("merge result unconfirmed")
                git(checkout, "fetch", "origin", merged["merge_commit_sha"])
                post_checkout, actual_tree = self._integration(checkout, base,
                    merged["merge_commit_sha"], "post")
                if actual_tree != expected_tree:
                    raise RuntimeError("merged tree differs from validated tree")
                post_checks, post_passed = run_checks(post_checkout, policy)
                if not post_passed:
                    raise RuntimeError("post-merge validation failed")
            except Exception as error:
                pause_path.write_text(json.dumps({"repo": repo, "pr": number,
                    "expected_tree": expected_tree, "reason": str(error)}))
                self.gitea.create_issue_once(repo, f"<!-- night-merge-incident:{repo}:{target} -->",
                    f"Automatic merge incident on {target}",
                    f"PR #{number} was submitted for merge but post-merge proof failed: {error}. "
                    "Further automatic merges to this target are paused; no blind revert was attempted.",
                    repo.split("/", 1)[0])
                raise RuntimeError("post-merge proof failed; target paused") from error
            return {"head": head, "base": base, "merge": merged.get("merge_commit_sha"),
                "checks": evidence, "post_checks": post_checks,
                "strategy": policy.get("merge_strategy", "merge")}

    def required_statuses(self, repo, target, head, policy):
        """Check every registered server context, including absent or pending results."""
        required = set(policy.get('required_statuses', []))
        try:
            protection = self.gitea.request('GET', f'/repos/{repo}/branch_protections/{urllib.parse.quote(target, safe="")}')
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            protection = {}
        required.update(protection.get('status_check_contexts') or [])
        if not required:
            return
        statuses = self.gitea.pages(f'/repos/{repo}/commits/{head}/statuses')
        latest = {}
        for status in sorted(statuses, key=lambda item: item['id'], reverse=True):
            latest.setdefault(status['context'], status.get('status'))
        if any(latest.get(context) != 'success' for context in required):
            raise ValueError('required Gitea status missing or not successful')
