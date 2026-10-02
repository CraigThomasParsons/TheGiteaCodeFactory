"""Deterministic validation and merge gates independent from reviewing agents."""
from __future__ import annotations

import json
import subprocess
from .runtime import inherited_locks

POLICY_PATH = ".gitea/night-merge.json"


def git(repo, *arguments, check=True):
    """Run Git without a shell and return stripped output."""
    return subprocess.run(["git", "-C", repo, *arguments], check=check, capture_output=True,
        text=True, pass_fds=inherited_locks())


def policy_at(repo: str, base_sha: str):
    """Load trusted gates from the pinned target revision."""
    result = git(repo, "show", f"{base_sha}:{POLICY_PATH}", check=False)
    if result.returncode != 0:
        raise ValueError("missing validation policy")
    policy = json.loads(result.stdout)
    if policy.get("version") != 1 or not policy.get("required_checks"):
        raise ValueError("validation policy has no meaningful required checks")
    for command in policy["required_checks"]:
        if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
            raise ValueError("required checks must be nonempty argv arrays")
    strategy = policy.get("merge_strategy", "merge")
    if strategy not in ("merge", "rebase", "rebase-merge", "squash"):
        raise ValueError("unsupported merge strategy")
    return policy


def review_passes(report: dict, head_sha: str, base_sha: str):
    """Require complete pinned review evidence and zero blocking findings."""
    if report.get("head") != head_sha or report.get("base") != base_sha:
        return False, "review is stale"
    if report.get("specification_complete") is not True:
        return False, "specification is missing or ambiguous"
    if not all(isinstance(report.get(axis), list) for axis in ('standards', 'specification')):
        return False, 'review axis evidence missing'
    findings = report.get("standards", []) + report.get("specification", [])
    unresolved = [finding for finding in findings if finding.get("blocking") and (
        finding.get("status") not in ("fixed", "dismissed")
        or not finding.get('verification'))]
    if unresolved:
        return False, "blocking findings remain"
    return True, "review gates pass"


def run_checks(repo: str, policy: dict):
    """Execute every trusted command; missing, skipped or nonzero never passes."""
    evidence = []
    for command in policy["required_checks"]:
        try:
            completed = subprocess.run(command, cwd=repo, capture_output=True, text=True,
                pass_fds=inherited_locks())
            evidence.append({"command": command, "exit_code": completed.returncode,
                "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:]})
        except (OSError, subprocess.TimeoutExpired) as error:
            evidence.append({"command": command, "exit_code": None, "error": str(error)})
    return evidence, bool(evidence) and all(item.get("exit_code") == 0 for item in evidence)
