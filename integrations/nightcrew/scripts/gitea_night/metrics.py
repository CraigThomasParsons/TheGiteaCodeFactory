"""Report Gitea PR backlog and durable worker event metrics."""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

from .gitea import Gitea
from .worker import token


def report(gitea: Gitea, owner: str, state_dir: Path):
    """Collect operational measurements separately from merge evidence."""
    now = datetime.datetime.now(datetime.timezone.utc)
    pulls = []
    for repository in gitea.owned_repositories(owner):
        for pull in gitea.open_pulls(repository["full_name"]):
            created = datetime.datetime.fromisoformat(pull["created_at"])
            pulls.append({"repo": repository["full_name"], "number": pull["number"],
                "age_hours": round((now - created).total_seconds() / 3600, 2),
                "state": next((label["name"] for label in pull.get("labels", [])
                    if label["name"].startswith("night:")), "unclassified")})
    events = []
    path = state_dir / "metrics.jsonl"
    if path.exists():
        events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    durations = []
    for event in events:
        if event.get("started_at") and event.get("finished_at"):
            start = datetime.datetime.fromisoformat(event["started_at"])
            finish = datetime.datetime.fromisoformat(event["finished_at"])
            durations.append((finish - start).total_seconds())
    receipts = [event.get("receipt", {}) for event in events]
    return {"backlog_size": len(pulls), "oldest_pr_age_hours": max(
        [pull["age_hours"] for pull in pulls], default=0), "pulls": pulls,
        "provider_failures": sum(bool(receipt.get("provider_failures") or receipt.get("provider_failure"))
            for receipt in receipts),
        "job_failures": sum("failed" in event for event in events),
        "repair_cycles": sum(event.get("stage") == "resolve" for event in events),
        "duplicate_comments_prevented": sum(receipt.get("comment_published") is False for receipt in receipts),
        "missing_check_blockers": sum("validation_bootstrap_issue" in receipt for receipt in receipts),
        "check_failures": sum("validation" in json.dumps(event.get("failed", {})).lower() for event in events),
        "post_merge_failures": sum(event.get("stage") == "review" and
            "post-merge" in json.dumps(event.get("failed", {})).lower() for event in events),
        "average_job_seconds": round(sum(durations) / len(durations), 2) if durations else 0,
        "events": len(events)}


def main(argv=None):
    """CLI entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--gitea-url", required=True)
    parser.add_argument("--gitea-token", default="~/.config/pulse/gitea_token")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--state-dir", default="~/.local/state/gitea-night")
    arguments = parser.parse_args(argv)
    print(json.dumps(report(Gitea(arguments.gitea_url, token(arguments.gitea_token)), arguments.owner,
        Path(arguments.state_dir).expanduser()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
