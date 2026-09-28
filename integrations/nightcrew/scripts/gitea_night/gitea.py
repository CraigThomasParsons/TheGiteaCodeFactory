"""Small, origin-fenced Gitea API client used by the local worker."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Reject redirects so credentials never cross an origin boundary."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        raise urllib.error.HTTPError(request.full_url, code, "redirect refused", headers, file_pointer)


class Gitea:
    """Call one configured Gitea origin; no GitHub endpoint is representable."""

    def __init__(self, base_url: str, token: str):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Gitea URL must be an absolute HTTP(S) URL")
        if parsed.hostname in ('github.com', 'api.github.com') or (parsed.hostname or '').endswith('.github.com'):
            raise ValueError('GitHub is excluded from this worker')
        self.base_url = base_url.rstrip("/") + "/api/v1"
        self.origin = (parsed.scheme, parsed.netloc)
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, method: str, path: str, body=None):
        """Perform one authenticated JSON request within the configured origin."""
        url = self.base_url + "/" + path.lstrip("/")
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme, parsed.netloc) != self.origin:
            raise ValueError("request escaped configured Gitea origin")
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", "token " + self.token)
        request.add_header("Accept", "application/json")
        request.add_header("Content-Type", "application/json")
        with self.opener.open(request, timeout=30) as response:
            payload = response.read()
            return None if not payload else json.loads(payload)

    def pages(self, path: str):
        """Exhaust a collection even when the server silently caps page size."""
        items = []
        separator = "&" if "?" in path else "?"
        for page in range(1, 10001):
            batch = self.request("GET", f"{path}{separator}limit=50&page={page}")
            if not batch:
                return items
            items.extend(batch)
        raise RuntimeError("pagination limit exceeded")

    def repository(self, full_name: str):
        """Read a repository by owner/name."""
        return self.request("GET", "/repos/" + full_name)

    def pull(self, full_name: str, number: int):
        """Read one pull request."""
        return self.request("GET", f"/repos/{full_name}/pulls/{number}")

    def comments(self, full_name: str, number: int):
        """Read every issue comment for a pull request."""
        return self.pages(f"/repos/{full_name}/issues/{number}/comments")

    def comment_once(self, full_name: str, number: int, marker: str, body: str):
        """Publish one marker-keyed comment and suppress revision duplicates."""
        if any(marker in comment.get("body", "") for comment in self.comments(full_name, number)):
            return False
        self.request("POST", f"/repos/{full_name}/issues/{number}/comments", {"body": marker + "\n" + body})
        return True

    def push_mirrors(self, full_name: str):
        """Discover outbound mirrors before enrollment."""
        return self.pages(f"/repos/{full_name}/push_mirrors")

    def github_writing_hooks(self, full_name: str):
        """Conservatively identify repository hooks targeting GitHub."""
        hooks = self.pages(f"/repos/{full_name}/hooks")
        return [hook for hook in hooks if "github.com" in json.dumps(hook.get("config", {})).lower()]

    def outbound_writes(self, full_name: str):
        """Return configured integrations which may write outside this Gitea."""
        return self.push_mirrors(full_name) + self.github_writing_hooks(full_name)

    def owned_repositories(self, owner: str):
        """Discover every nonarchived repository actually owned by the account."""
        repositories = self.pages(f"/users/{owner}/repos?archived=false")
        return [repo for repo in repositories if repo.get("owner", {}).get("login") == owner and not repo.get("archived")]

    def open_pulls(self, full_name: str):
        """Discover all open pull requests, including drafts."""
        return self.pages(f"/repos/{full_name}/pulls?state=open")

    def ensure_labels(self, full_name: str, names):
        """Create missing workflow labels and return their numeric IDs."""
        labels = {label["name"]: label for label in self.pages(f"/repos/{full_name}/labels")}
        colors = {"night:ready-for-review": "1d76db", "night:ready-for-resolution": "d93f0b",
            "night:ready-to-merge": "0e8a16", "night:blocked": "b60205", "night:hold": "5319e7"}
        for name in names:
            if name not in labels:
                labels[name] = self.request("POST", f"/repos/{full_name}/labels",
                    {"name": name, "color": colors[name], "description": "TheNightCrew PR workflow state"})
        return {name: labels[name]["id"] for name in names}

    def set_night_state(self, full_name: str, number: int, state: str):
        """Replace only workflow-state labels while preserving repository labels."""
        names = ("night:ready-for-review", "night:ready-for-resolution", "night:ready-to-merge",
            "night:blocked", "night:hold")
        ids = self.ensure_labels(full_name, names)
        issue = self.request("GET", f"/repos/{full_name}/issues/{number}")
        if state != 'night:hold' and any(label.get('name') == 'night:hold' for label in issue.get('labels', [])):
            return
        keep = [label["id"] for label in issue.get("labels", []) if label.get("name") not in names]
        if state:
            keep.append(ids[state])
        self.request("PUT", f"/repos/{full_name}/issues/{number}/labels", {"labels": keep})

    def create_issue_once(self, full_name: str, marker: str, title: str, body: str, assignee: str):
        """Create one marker-keyed assigned task and preserve it as audit evidence."""
        for issue in self.pages(f"/repos/{full_name}/issues?state=all"):
            if marker in (issue.get("body") or ""):
                return issue, False
        issue = self.request("POST", f"/repos/{full_name}/issues", {
            "title": title, "body": marker + "\n" + body, "assignees": [assignee]})
        return issue, True
