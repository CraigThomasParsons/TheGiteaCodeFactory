#!/usr/bin/env python3
"""Bench rate-limited accounts and prepare same-task handoffs; never launch or kill agents."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import tempfile
import time


def route(config, ledger, packet, event, now=None):
    now = time.time() if now is None else now
    if event.get('kind') != 'rate_limited':
        raise ValueError('Only confirmed rate-limit events authorize automatic failover')
    if event.get('writer_stopped') is not True:
        raise ValueError('Reconcile the old writer before transferring ownership')
    for key in ('task', 'repo', 'branch', 'worktree', 'phase', 'head_sha', 'evidence', 'agent', 'attempted_accounts'):
        if key not in packet:
            raise ValueError('Handoff packet missing ' + key)
    agents = config['agents']
    current = next((a for a in agents if a['id'] == packet['agent']), None)
    if not current or event.get('agent') != current['id']:
        raise ValueError('Rate-limit event does not identify the current agent')
    previous = ledger.get(current['account'], {})
    failures = previous.get('failures', 0) + 1
    reset = event.get('reset_at')
    if reset is not None:
        until = datetime.fromisoformat(reset.replace('Z', '+00:00'))
        if until.tzinfo is None:
            raise ValueError('reset_at must include a timezone')
        until = until.timestamp()
        if until <= now:
            raise ValueError('Reset time must be in the future')
    else:
        until = now + min(60 * 2 ** min(failures - 1, 9), 21600)
    until = max(until, previous.get('until', 0))
    ledger[current['account']] = {'until': until, 'failures': failures, 'observed_at': now}
    attempted = list(dict.fromkeys(packet['attempted_accounts'] + [current['account']]))
    candidates = [a for a in agents if a.get('enabled') is True
                  and a.get('installed') is True
                  and packet['phase'] in a['capabilities']
                  and a['account'] not in attempted
                  and ledger.get(a['account'], {}).get('until', 0) <= now]
    # Config order is the operator's preference, not an inferred model ranking.
    selected = candidates[0] if candidates else None
    next_packet = dict(packet, attempted_accounts=attempted)
    next_packet['previous_agent'] = current['id']
    next_packet['agent'] = selected['id'] if selected else None
    next_packet['status'] = 'handoff_ready' if selected else 'parked'
    next_packet['reason'] = 'rate_limited'
    next_packet['benched_until'] = datetime.fromtimestamp(until, timezone.utc).isoformat()
    return next_packet


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.')
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(value, out, indent=2)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'packet', 'event', 'state', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.state.parent.mkdir(parents=True, exist_ok=True)
    with args.state.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.output.exists():
            raise ValueError('Output exists; reconcile that handoff instead of routing twice')
        ledger = json.loads(args.state.read_text()) if args.state.exists() else {}
        packet = route(json.loads(args.config.read_text()), ledger,
                       json.loads(args.packet.read_text()), json.loads(args.event.read_text()))
        # A crash between these writes leaves the account safely benched; the controller
        # must inspect ledger/old writer and create a new attempt, never launch blindly.
        atomic(args.state, ledger)
        atomic(args.output, packet)
        print(json.dumps({'status': packet['status'], 'agent': packet['agent'], 'handoff': str(args.output)}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(str(exc))
