#!/usr/bin/env python3
"""Classify one normalized worker observation without scraping adapter-specific text."""

from __future__ import annotations

import json
import sys
from typing import Any


def classify(observation: dict[str, Any]) -> str:
    """Return the fail-closed execution state for an observation."""
    if observation.get("scopeViolation"):
        return "BLOCKED_SCOPE"
    if observation.get("gateFailure"):
        return "BLOCKED_GATE"
    if observation.get("approvalRequired"):
        return "WAITING_APPROVAL"
    if observation.get("providerFailure"):
        return "WAITING_PROVIDER"
    if observation.get("working") or observation.get("subagentsWorking"):
        return "WORKING"
    if observation.get("receiptValid") and observation.get("evidenceSatisfied"):
        return "DONE"
    if not observation.get("processAlive", True):
        return "FAILED_INFRASTRUCTURE"
    idle_streak = observation.get("idleStreak", 0)
    if not isinstance(idle_streak, int) or idle_streak < 0:
        raise ValueError("idleStreak must be a non-negative integer")
    return "STALLED" if idle_streak >= 2 else "IDLE"


def main() -> int:
    """Read an observation from stdin and print its classification."""
    try:
        observation = json.load(sys.stdin)
        if not isinstance(observation, dict):
            raise ValueError("observation must be a JSON object")
        print(json.dumps({"state": classify(observation)}))
    except (json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
