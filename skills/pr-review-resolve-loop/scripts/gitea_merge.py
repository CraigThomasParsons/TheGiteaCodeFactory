#!/usr/bin/env python3
"""Inspect or merge one Gitea PR using a current-head clean review receipt."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import urllib.error
import http.client
import stat
import urllib.parse
import urllib.request

SERVER = os.environ.get('GITEA_SERVER_URL', '').rstrip('/')

class Blocked(Exception):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Blocked('API redirect refused; verify the configured Gitea host')

class Api:
    def __init__(self):
        tokenfile = Path(os.environ.get('GITEA_TOKEN_FILE', str(Path.home() / '.config/gitea-code-factory/token')))
        self.token = os.environ.get('GITEA_TOKEN', '').strip() or (tokenfile.read_text().strip() if tokenfile.exists() else '')
        if not self.token:
            raise Blocked('Gitea token missing: GITEA_TOKEN or GITEA_TOKEN_FILE')
        if not SERVER.startswith(('http://', 'https://')):
            raise Blocked('Set GITEA_SERVER_URL to the intended Gitea server')
        self.opener = urllib.request.build_opener(NoRedirect)

    def call(self, method, path, body=None):
        request = urllib.request.Request(SERVER + '/api/v1' + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization': 'token ' + self.token, 'Content-Type': 'application/json'}, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raise Blocked(f'Gitea HTTP {exc.code}; operation not confirmed') from None
        except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError):
            raise Blocked('Gitea response unavailable or invalid; operation not confirmed') from None

    def statuses(self, prefix, sha):
        rows = []
        for page in range(1, 1001):
            batch = self.call('GET', f'{prefix}/commits/{sha}/statuses?limit=50&page={page}')
            if not isinstance(batch, list):
                raise Blocked('Invalid commit status response')
            rows.extend(batch)
            if not batch:
                return rows
        raise Blocked('Status pagination exceeded bound')


def validate(pr, receipt, statuses, repo, number):
    if receipt.get('server') != SERVER or receipt.get('repo') != repo or receipt.get('pr') != number:
        raise Blocked('Receipt repository/PR identity mismatch')
    head, base = pr.get('head', {}).get('sha'), pr.get('base', {}).get('sha')
    if not head or receipt.get('head_sha') != head or not base or receipt.get('base_sha') != base:
        raise Blocked('Review is stale; re-review the current head and base')
    identities = {'base_ref': pr.get('base', {}).get('ref'), 'head_ref': pr.get('head', {}).get('ref'),
                  'head_repo': pr.get('head', {}).get('repo', {}).get('full_name')}
    if any(not value or receipt.get(key) != value for key, value in identities.items()):
        raise Blocked('Review branch identity changed; re-review the target and source')
    if pr.get('state') != 'open' or pr.get('merged') or pr.get('draft') is not False:
        raise Blocked('PR must be open, unmerged and non-draft')
    if pr.get('mergeable') is not True:
        raise Blocked('Gitea has not confirmed mergeability')
    labels = {row['name'] for row in pr.get('labels', [])}
    if 'review:clear' not in labels or labels.intersection({'review:findings', 'review:needs-human', 'review:requested', 'review:in-progress', 'review:resolving'}):
        raise Blocked('PR lacks review:clear or has a conflicting review label')
    if receipt.get('schema_version') != 1 or receipt.get('findings') != []:
        raise Blocked('Receipt must be version 1 with no unresolved findings')
    if receipt.get('standards_review') != 'clear' or receipt.get('spec_review') != 'clear':
        raise Blocked('Both independent review axes must be clear')
    required = receipt.get('required_contexts')
    if not isinstance(required, list) or not required or any(not isinstance(x, str) or not x for x in required):
        raise Blocked('Receipt must list actual required validation contexts')
    latest = {}
    for row in statuses:
        context = row.get('context')
        if context and (context not in latest or row.get('id', 0) > latest[context].get('id', 0)):
            latest[context] = row
    if any(name not in latest or latest[name].get('status') != 'success' for name in required):
        raise Blocked('Required current-head validation missing, pending or failed')
    if any(row.get('status') != 'success' for row in latest.values()):
        raise Blocked('A published current-head status is pending or failing')
    return head


def run(api, repo, number, receipt, method, execute=False):
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo) or number < 1:
        raise Blocked('Invalid repository or PR number')
    if method not in {'merge', 'squash', 'rebase', 'rebase-merge', 'fast-forward-only'}:
        raise Blocked('Unsupported merge method')
    prefix = '/repos/' + repo
    path = f'{prefix}/pulls/{number}'
    pr = api.call('GET', path)
    statuses = api.statuses(prefix, pr.get('head', {}).get('sha'))
    head = validate(pr, receipt, statuses, repo, number)
    if not execute:
        return {'status': 'eligible', 'head': head, 'mutation': False}
    # Recheck labels, head/base and statuses immediately before the guarded mutation.
    current = api.call('GET', path)
    validate(current, receipt, api.statuses(prefix, head), repo, number)
    try:
        api.call('POST', path + '/merge', {
            'do': method, 'head_commit_id': head, 'force_merge': False,
            'delete_branch_after_merge': False, 'merge_when_checks_succeed': False})
    except Blocked:
        # A timeout could occur after acceptance. Inspect once, never retry the POST.
        observed = api.call('GET', path)
        return verified_merge(observed, head)
    return verified_merge(api.call('GET', path), head)


def verified_merge(observed, head):
    merge_sha = observed.get('merge_commit_sha')
    if (observed.get('merged') is not True or observed.get('head', {}).get('sha') != head
            or not isinstance(merge_sha, str) or not re.fullmatch(r'[0-9a-f]{40}', merge_sha)):
        raise Blocked('Merge revision not verified; inspect server state before retry')
    return {'status': 'merged', 'head': head, 'merge_commit': merge_sha}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--pr', type=int, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--method', choices=['merge', 'squash', 'rebase', 'rebase-merge', 'fast-forward-only'], required=True)
    parser.add_argument('--execute', action='store_true', help='Merge if eligible; default is read-only')
    args = parser.parse_args()
    state = Path.home() / '.local/state/gitea-pr-review-resolve'
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt_path = args.receipt.resolve()
    if not receipt_path.is_relative_to(state.resolve()):
        raise Blocked('Receipt must be local controller state, never a file from the PR checkout')
    protected_paths = [state, receipt_path, *[p for p in receipt_path.parents if p.is_relative_to(state.resolve())]]
    for protected in protected_paths:
        info = protected.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
            raise Blocked('Controller state/receipt must be owned by this user and not writable by others')
    with (state / 'merge.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Blocked('Another merge controller owns the lock') from None
        receipt = json.loads(receipt_path.read_text())
        result = run(Api(), args.repo, args.pr, receipt, args.method, args.execute)
        print(json.dumps(result))
        with (state / 'merges.jsonl').open('a') as log:
            log.write(json.dumps({'repo': args.repo, 'pr': args.pr, **result}) + '\n')

if __name__ == '__main__':
    try:
        main()
    except (Blocked, ValueError, OSError, KeyError) as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc)}))
        raise SystemExit(1)
