import importlib.util, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('pipeline',Path(__file__).with_name('pipeline.py'))
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
class PipelineTests(unittest.TestCase):
 def test_clone_transports_share_repository_lock_identity(self):
  for remote in ('git@host:owner/repo.git','ssh://git@host:2222/owner/repo.git','https://host/owner/repo.git'):
   self.assertEqual(m.repository_identity(remote),'owner/repo')
 def test_rejects_false_completion_shape(self):
  for value in ({'decision':'merged','reason':'x'},{'decision':'complete'},{'decision':'continue','reason':5}):
   with self.assertRaises(ValueError): m.validate(value,m.TICK)
 def test_failure_never_accepts_receipt(self):
  with tempfile.TemporaryDirectory() as td:
   def fake(cmd,**kwargs):
    Path(cmd[cmd.index('-o')+1]).write_text(json.dumps({'decision':'complete','reason':'fake'}))
    return type('R',(),{'returncode':1,'communicate':lambda self,*a,**kw: None})()
   with patch.object(m.subprocess,'Popen',side_effect=fake): r=m.execute(td,'test',Path(td)/'attempt','tick')
   self.assertIsNone(r['receipt']); self.assertEqual(r['exit_code'],1)
 def test_missing_output_stops(self):
  with tempfile.TemporaryDirectory() as td, patch.object(m.subprocess,'Popen',return_value=type('R',(),{'returncode':0,'communicate':lambda self,*a,**kw: None})()):
   r=m.execute(td,'test',Path(td)/'attempt','tick'); self.assertIsNone(r['receipt'])
 def test_unique_attempt_refuses_stale_output(self):
  with tempfile.TemporaryDirectory() as td:
   with self.assertRaises(FileExistsError): m.execute(td,'test',Path(td),'tick')
 def test_review_wait_stops_without_resetting_queue(self):
  with tempfile.TemporaryDirectory() as td:
   state=Path(td)/'state.json'; initial={'workspace':td,'status':'running','umbrella_url':'https://example.test/issue/1','queue':[{'issue':2,'phase':'REVIEW'}]}; m.atomic(state,initial)
   with patch.object(m,'execute',return_value={'exit_code':0,'receipt':{'decision':'awaiting_review','reason':'PR ready'}}) as execute:
    m.run(state,1); self.assertEqual(execute.call_count,1)
   self.assertEqual(json.loads(state.read_text()),initial)
   self.assertEqual(json.loads((state.parent/'supervisor-status.json').read_text())['status'],'awaiting_review')
 def test_duplicate_supervisor_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   state=Path(td)/'state.json'; m.atomic(state,{'workspace':td})
   with state.with_suffix('.lock').open('a') as f:
    m.fcntl.flock(f,m.fcntl.LOCK_EX|m.fcntl.LOCK_NB)
    with self.assertRaisesRegex(ValueError,'already owns'): m.run(state,1)
 def test_tick_timeout_retains_pid_and_blocks_retry(self):
  with tempfile.TemporaryDirectory() as td:
   process=type('R',(),{'pid':12345,'communicate':lambda self,*a,**kw: (_ for _ in ()).throw(m.subprocess.TimeoutExpired('codex',1200))})()
   with patch.object(m.subprocess,'Popen',return_value=process):
    r=m.execute(td,'test',Path(td)/'attempt','tick')
   self.assertEqual(r['live_pid'],12345); self.assertEqual(r['exit_code'],124)
   state=Path(td)/'state.json'; m.atomic(state,{'workspace':td,'queue':[]})
   m.atomic(Path(td)/'supervisor-status.json',{'live_pid':12345})
   with self.assertRaisesRegex(ValueError,'unreconciled'): m.run(state,1)
 def test_phase_adapter_requires_installed_skill(self):
  with tempfile.TemporaryDirectory() as td, patch.object(m,'SKILL',Path(td)/'slice-pipeline'):
   with self.assertRaisesRegex(ValueError,'Missing phase skill'): m.phase_prompt('IMPL','issue packet')
 def test_each_phase_builds_self_contained_prompt(self):
  for phase in m.PHASE_SKILLS:
   prompt=m.phase_prompt(phase,'https://example.test/issues/42 — approved packet')
   self.assertIn('https://example.test/issues/42',prompt)
   self.assertIn(str(m.SKILL.parent/m.PHASE_SKILLS[phase]/'SKILL.md'),prompt)
 def test_completed_slice_still_gets_fresh_dispatch_observation(self):
  with tempfile.TemporaryDirectory() as td:
   state=Path(td)/'state.json'; m.atomic(state,{'workspace':td,'status':'complete','umbrella_url':'https://example.test/issue/1','queue':[]})
   with patch.object(m,'execute',return_value={'exit_code':0,'receipt':{'decision':'complete','reason':'outcome verified'}}) as execute:
    m.run(state,1); self.assertEqual(execute.call_count,1)
if __name__=='__main__': unittest.main()
