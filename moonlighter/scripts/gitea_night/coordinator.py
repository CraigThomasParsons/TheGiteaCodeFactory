"""Authenticated client for TheNightCrew's PR-stage coordinator API."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request


class Coordinator:
    """Create, claim and checkpoint durable PR-stage jobs."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, body=None):
        """Perform one coordinator request."""
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.base_url + path, data=data, method=method)
        request.add_header("Authorization", "Bearer " + self.token)
        request.add_header("Accept", "application/json")
        request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
            return None if not payload else json.loads(payload)

    def enqueue(self, repo: str, number: int, head: str, base: str, stage: str, attempt: int):
        """Idempotently admit one immutable PR stage."""
        path_repo = urllib.parse.quote(repo, safe="/")
        response = self.request("POST", f"/repos/{path_repo}/jobs", {
            "kind": "pull_request", "reference": str(number),
            "payload": {"head": head, "base": base, "stage": stage, "attempt": attempt}})
        return response["data"]

    def claim(self, stage: str, recover_stale: bool = True):
        """Atomically claim one job for the requested window stage."""
        recovery = "1" if recover_stale else "0"
        response = self.request("POST", "/claim-next?stage=" + urllib.parse.quote(stage) + "&recover_stale=" + recovery)
        return None if response is None else response["data"]

    def status(self, job: dict, status: str, receipt=None):
        """Transition the held job using its unguessable claim fence."""
        body = {"status": status, "claim_token": job["claim_token"]}
        if receipt is not None:
            body["receipt"] = receipt
        response = self.request("PATCH", f"/jobs/{job['id']}/status", body)
        return response["data"]

    def history(self):
        """Read authenticated receipts, never treating tracker comments as authority."""
        items = []
        for page in range(1, 10001):
            result = self.request("GET", f"/pr-jobs?page={page}")
            items.extend(result["data"])
            if page >= result["last_page"]:
                return items
        raise RuntimeError("coordinator history pagination exceeded")
