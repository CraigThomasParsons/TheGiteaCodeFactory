#!/usr/bin/env python3
"""Durable, single-owner tmux driver and fresh-context Codex phase adapter."""
import argparse, fcntl, hashlib, json, os, shlex, subprocess, sys, time, uuid
from pathlib import Path
from urllib.parse import urlsplit
import re
SKILL=Path(__file__).resolve().parents[1]
PHASE_SKILLS={'IMPL':'tdd','SIMPLIFY':'simplify','ARCHITECTURE':'improve-codebase-architecture','REVIEW':'code-review','PR':'tmux-pipeline'}


def repository_identity(origin):
    """Normalize URL and SCP transports to the owner/repo identity NightCrew uses."""
    if '://' in origin:
        path=urlsplit(origin).path
    elif re.match(r'[^/]+:[^/]', origin):
        path=origin.split(':',1)[1]
    else:
        raise ValueError('Remote must identify a hosted owner/repository')
    parts=path.strip('/').removesuffix('.git').split('/')
    if len(parts)!=2 or not all(re.fullmatch(r'[\w.-]+', part) for part in parts):
        raise ValueError('Remote must identify exactly owner/repository')
    return '/'.join(parts)

def phase_prompt(phase,packet):
    skillfile=SKILL.parent/PHASE_SKILLS[phase]/'SKILL.md'
    if not skillfile.is_file(): raise ValueError('Missing phase skill: '+str(skillfile))
    common=SKILL.parent/'tmux-pipeline/SKILL.md'
    return f"""Execute exactly the {phase} phase. Read {common}, then run the process in {skillfile}.
Use Codex skill invocation/read semantics, not Claude slash commands. The issue packet below defines scope.
Keep this context in its assigned phase; architecture and review must never be fused.
Never merge, enable auto-merge, force-push, reset hard, delete branches, edit oracle source, deploy,
or write outside the authorized repository. Use the existing account and provider.
Push ordinary in-scope commits; open the draft PR on the first implementation commit.
At completion return the structured phase receipt with phase {phase}; do not run the outer supervisor.
For PR, verify counts using the installed tmux-pipeline/scripts/verify-freshness.sh and current-head evidence.

Issue packet:
{packet}
"""

def atomic(path,data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('x') as f:
            os.chmod(tmp,0o600); json.dump(data,f,indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        tmp.unlink(missing_ok=True)

def schema(props):
    return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}
S={'type':'string'}; STRINGS={'type':'array','items':S}
TICK=schema({'decision':{'type':'string','enum':['continue','awaiting_review','blocked','complete']},'reason':S})
RECEIPT=schema({'issue_url':S,'phase':S,'base_sha':S,'head_sha':S,'changed_files':STRINGS,'scope_statement':S,
    'validation':{'type':'array','items':schema({'command':S,'exit_code':{'type':'integer'},'evidence_path':S})},
    'push_status':S,'pr_url':S,'discovered_issue_urls':STRINGS,'blockers':STRINGS,
    'status':{'type':'string','enum':['complete','blocked']},'next_phase':S})

def validate(value,spec):
    kind=spec['type']
    if kind=='object':
        if not isinstance(value,dict) or set(value)!=set(spec['required']): raise ValueError('Invalid result fields')
        for k,v in value.items(): validate(v,spec['properties'][k])
    elif kind=='array':
        if not isinstance(value,list): raise ValueError('Expected array')
        for v in value: validate(v,spec['items'])
    elif kind=='string':
        if not isinstance(value,str): raise ValueError('Expected string')
    elif kind=='integer':
        if type(value) is not int: raise ValueError('Expected integer')
    if 'enum' in spec and value not in spec['enum']: raise ValueError('Invalid state')

def execute(workspace,prompt,directory,kind):
    directory.mkdir(parents=True,exist_ok=False,mode=0o700)
    spec=TICK if kind=='tick' else RECEIPT
    atomic(directory/'schema.json',spec)
    (directory/'prompt.txt').write_text(prompt)
    cmd=['codex','exec','--skip-git-repo-check','-C',str(workspace),'--json','--output-schema',str(directory/'schema.json'),'-o',str(directory/'response.json'),'-']
    with (directory/'events.jsonl').open('w') as out, (directory/'stderr.log').open('w') as err:
        if kind == 'tick':
            # On timeout retain the process and evidence; never silently kill a worker.
            process=subprocess.Popen(cmd,stdin=subprocess.PIPE,text=True,stdout=out,stderr=err)
            try:
                process.communicate(prompt,timeout=1200)
                code=process.returncode
            except subprocess.TimeoutExpired:
                result={'exit_code':124,'attempt_dir':str(directory),'receipt':None,'live_pid':process.pid,
                        'error':'Supervisor exceeded 20 minutes; process left running. Reconcile it before resuming.'}
                atomic(directory/'result.json',result)
                return result
        else:
            code=subprocess.run(cmd,input=prompt,text=True,stdout=out,stderr=err).returncode
    result={'exit_code':code,'attempt_dir':str(directory),'receipt':None}
    if code==0:
        try:
            value=json.loads((directory/'response.json').read_text()); validate(value,spec); result['receipt']=value
        except (OSError,ValueError,TypeError) as e: result['error']='Invalid or missing response: '+str(e)
    atomic(directory/'result.json',result)
    return result

def name(state): return 'slice-'+hashlib.sha256(str(state.resolve()).encode()).hexdigest()[:12]
def run(state,interval,workspace=None):
    state=state.resolve()
    with state.with_suffix('.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Supervisor already owns this state')
        statusfile=state.parent/'supervisor-status.json'
        if statusfile.exists() and json.loads(statusfile.read_text()).get('live_pid'):
            raise ValueError('Previous supervisor timed out with an unreconciled process; inspect recorded PID/attempt before resuming')
        if not state.exists():
            if workspace is None: raise ValueError('Workspace required for first start')
            atomic(state,{'workspace':str(Path(workspace).resolve()),'status':'running','slice':None,
                          'umbrella_url':None,'queue':[],'tick':0,'parked_ticks':0,'scrum_countdown':30,
                          'last_action':'bootstrap; dispatcher must discover real tracker issues','blockers':[]})
        data=json.loads(state.read_text())
        workspace=Path(data['workspace']).resolve()
        if not workspace.is_dir(): raise ValueError('Workspace missing')
        if not isinstance(data.get('queue'),list): raise ValueError('Invalid queue')
        while True:
            attempt=state.parent/'ticks'/uuid.uuid4().hex
            prompt=f'''Read {SKILL / 'SKILL.md'} and {SKILL / 'references/protocol.md'}.
You are the durable supervisor performing exactly ONE tick for state {state}.
Do not launch another supervisor, call start/run, or implement product code yourself.
Use dispatcher, tmux-pipeline and scrum-master as needed for this single tick.
If state is bootstrap (no umbrella), dispatch the next eligible slice now under this driver lock,
create/reuse real assigned tracker issues and publish its packet before any implementation.
Re-observe live tracker and worker evidence. Resume from the state; do not reset its queue.
If the saved slice is complete, verify its merged AC, archive its queue/receipts under completed_slices,
and dispatch the next dependency-ready slice without erasing the prior history. If the entire outcome
is complete, confirm that from current evidence and return complete. Never treat saved complete as a no-op.
Take at most one orchestration action and atomically checkpoint state with tracker links.
Never merge, enable auto-merge, deploy, force-push, edit oracle source, or borrow another account.
Return continue only while useful authorized execution remains. Stop at review waiting or a real blocker.
Return the required decision/reason JSON. A phase receipt needs semantic verification before advancing.
'''
            result=execute(workspace,prompt,attempt,'tick')
            if result['exit_code'] or result['receipt'] is None:
                atomic(state.parent/'supervisor-status.json',{'status':'blocked','reason':'Supervisor failed; inspect private attempt logs','attempt':str(attempt),'live_pid':result.get('live_pid')})
                return
            decision=result['receipt']['decision']
            atomic(state.parent/'supervisor-status.json',{'status':decision,'reason':result['receipt']['reason'],'attempt':str(attempt)})
            if decision!='continue': return
            until=time.monotonic()+interval
            while time.monotonic()<until: time.sleep(min(1,max(0,until-time.monotonic())))

def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='cmd',required=True)
    for action in ('start','run','status'):
        a=sub.add_parser(action); a.add_argument('--state',type=Path,required=True); a.add_argument('--interval',type=int,default=60); a.add_argument('--workspace',type=Path)
    a=sub.add_parser('phase'); a.add_argument('--phase',choices=list(PHASE_SKILLS),required=True); a.add_argument('--worktree',type=Path,required=True); a.add_argument('--prompt',type=Path,required=True); a.add_argument('--result',type=Path,required=True)
    a=p.parse_args()
    if a.cmd=='phase':
        target=a.result.resolve(); target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        # One OS lock per worktree prevents simultaneous adapters from writing it.
        wt=a.worktree.resolve()
        lockroot=Path.home()/'.local/state/slice-pipeline/worktree-locks'; lockroot.mkdir(parents=True,exist_ok=True,mode=0o700)
        origin=subprocess.run(['git','-C',str(wt),'config','--get','remote.origin.url'],capture_output=True,text=True,check=True).stdout.strip()
        branch=subprocess.run(['git','-C',str(wt),'branch','--show-current'],capture_output=True,text=True,check=True).stdout.strip()
        sharedroot=Path.home()/'.local/state/gitea-night/branches'; sharedroot.mkdir(parents=True,exist_ok=True,mode=0o700)
        repository_key=repository_identity(origin)
        with (lockroot/hashlib.sha256(str(wt).encode()).hexdigest()).open('a') as lock, \
             (sharedroot/(hashlib.sha256(f'{repository_key}:{branch}'.encode()).hexdigest()+'.lock')).open('a') as shared_lock:
            try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: raise ValueError('Another phase owns this worktree')
            try: fcntl.flock(shared_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: raise ValueError('Another worker owns this repository branch')
            if target.exists(): raise ValueError('Result exists; use a new attempt path after reconciling previous evidence')
            prompt=phase_prompt(a.phase,a.prompt.read_text())
            result=execute(wt,prompt,target.with_suffix('.attempt'),'phase')
            if result['receipt'] and result['receipt']['phase'] != a.phase:
                result['receipt']=None
                result['error']='Receipt phase does not match the dispatched phase'
            atomic(target,result)
            return 0 if result['exit_code']==0 and result['receipt'] else 1
    state=a.state.resolve()
    if a.interval<1: raise ValueError('Interval must be positive')
    if a.cmd=='run':
        state.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        run(state,a.interval,a.workspace)
    elif a.cmd=='status':
        alive=subprocess.run(['tmux','has-session','-t',name(state)],capture_output=True).returncode==0
        print(json.dumps({'session':name(state),'alive':alive,'state':str(state),'last':json.loads((state.parent/'supervisor-status.json').read_text()) if (state.parent/'supervisor-status.json').exists() else None},indent=2))
    else:
        if not state.is_file() and a.workspace is None: raise ValueError('Pass --workspace for first start')
        session=name(state)
        if subprocess.run(['tmux','has-session','-t',session],capture_output=True).returncode==0:
            print('Supervisor session already exists: '+session); return 0
        argv=[sys.executable,str(Path(__file__).resolve()),'run','--state',str(state),'--interval',str(a.interval)]
        if a.workspace: argv.extend(['--workspace',str(a.workspace.resolve())])
        cmd=shlex.join(argv)
        subprocess.run(['tmux','new-session','-d','-s',session,cmd],check=True)
        print('Started '+session+'; inspect status and first tick before claiming healthy delivery')
    return 0
if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as e: print(str(e),file=sys.stderr); sys.exit(1)
