#!/usr/bin/env python3
"""Check deterministic, green behavior in two oracle and two port JSON reports."""
import argparse
import json
from pathlib import Path


def compare(reports):
    for report in reports:
        if not isinstance(report, dict) or not report:
            raise ValueError('Each report must contain scenarios')
        for name, outcome in report.items():
            if not isinstance(outcome, dict) or outcome.get('status') != 'passed' or 'observations' not in outcome:
                raise ValueError(f'Scenario {name} is missing, red, skipped, or lacks observations')
    oracle1, oracle2, port1, port2 = [json.dumps(r, sort_keys=True, allow_nan=False, separators=(",", ":")) for r in reports]
    if oracle1 != oracle2 or port1 != port2:
        raise ValueError('Nondeterministic lane: repeated runs differ')
    if oracle1 != port1:
        raise ValueError('Behavior parity mismatch (including missing or extra scenarios)')
    return len(reports[0])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', type=Path, nargs=4, metavar='REPORT')
    args = parser.parse_args()
    try:
        count = compare([json.loads(p.read_text()) for p in args.reports])
        print(f'PASS: {count} scenarios, both lanes green and deterministic')
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + '\n')
