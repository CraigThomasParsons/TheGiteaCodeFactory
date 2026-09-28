#!/usr/bin/env python3
"""Small Gitea adapter; JSON body files, paginated discovery, no merge endpoint."""
import argparse, json, os, re, sys, urllib.request, urllib.error, urllib.parse
from pathlib import Path
BASE=os.environ.get('GITEA_SERVER_URL','').rstrip('/')+'/api/v1'
def request(method,path,data=None,query=None):
    if not re.fullmatch(r'/repos/[\w.-]+/[\w.-]+/(issues|pulls)(/\d+)?(/comments|/reviews|/commits)?',path):
        raise ValueError('Unsupported route; use repository issue/PR metadata routes only')
    if method not in ('GET','POST','PATCH'): raise ValueError('Unsupported method')
    tokenfile=Path(os.environ.get('GITEA_TOKEN_FILE', str(Path.home()/'.config/gitea-code-factory/token')))
    token=os.environ.get('GITEA_TOKEN','').strip() or (tokenfile.read_text().strip() if tokenfile.exists() else '')
    if not token: raise ValueError('Gitea token missing from GITEA_TOKEN or GITEA_TOKEN_FILE')
    if not BASE.startswith(('http://','https://')): raise ValueError('Set GITEA_SERVER_URL')
    url=BASE+path+("?"+urllib.parse.urlencode(query) if query else "")
    req=urllib.request.Request(url,data=json.dumps(data).encode() if data is not None else None,
        headers={'Authorization':'token '+token,'Content-Type':'application/json'},method=method)
    with urllib.request.urlopen(req,timeout=30) as response: return json.load(response)
def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='cmd',required=True)
    ls=sub.add_parser('list'); ls.add_argument('--repo',required=True); ls.add_argument('--state',choices=['all','open','closed'],default='all')
    req=sub.add_parser('request'); req.add_argument('method',choices=['GET','POST','PATCH']); req.add_argument('path'); req.add_argument('--body-file',type=Path)
    a=p.parse_args()
    if a.cmd=='request':
        print(json.dumps(request(a.method,a.path,json.loads(a.body_file.read_text()) if a.body_file else None),indent=2)); return
    if not re.fullmatch(r'[\w.-]+/[\w.-]+',a.repo): raise ValueError('Invalid repo')
    rows=[]; page=1
    while True:
        batch=request('GET',f'/repos/{a.repo}/issues',query={'state':a.state,'limit':50,'page':page})
        if not isinstance(batch,list): raise ValueError('Expected issue list')
        rows.extend(batch)
        if not batch: break
        page+=1
        if page>1000: raise ValueError('Pagination exceeded limit; refuse partial discovery')
    print(json.dumps(rows,indent=2))
if __name__=='__main__':
    try: main()
    except urllib.error.HTTPError as e: print(f'Gitea HTTP {e.code}; request not completed',file=sys.stderr); sys.exit(1)
    except Exception as e: print(str(e),file=sys.stderr); sys.exit(1)
