import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
coach, parity, installer = module('coach'), module('parity'), module('install-skills')

class CoachTests(unittest.TestCase):
    def setUp(self):
        self.config = {'agents': [dict(id='a', account='one', enabled=True, installed=True, capabilities=['IMPL']),
                                  dict(id='b', account='two', enabled=True, installed=True, capabilities=['IMPL'])]}
        self.packet = dict(task='issue', repo='o/r', branch='feature', worktree='/tmp/w', phase='IMPL',
                           head_sha='a'*40, evidence=['log'], agent='a', attempted_accounts=[])
        self.event = dict(kind='rate_limited', agent='a', writer_stopped=True)
        self.ledger = {}
    def route(self): return coach.route(self.config, self.ledger, self.packet, self.event, now=1000)
    def test_handoff_preserves_task(self):
        result = self.route()
        self.assertEqual(result['agent'], 'b')
        for key in ['task','repo','branch','worktree','phase','head_sha','evidence']:
            self.assertEqual(result[key], self.packet[key])
        self.assertEqual(self.ledger['one']['until'], 1060)
    def test_existing_provider_reset_is_not_shortened(self):
        self.ledger['one'] = dict(until=100000, failures=1)
        self.route()
        self.assertEqual(self.ledger['one']['until'], 100000)
    def test_live_writer_blocks(self):
        self.event['writer_stopped'] = False
        with self.assertRaises(ValueError): self.route()
        self.assertEqual(self.ledger, {})
    def test_auth_failure_blocks(self):
        self.event['kind'] = 'authentication_error'
        with self.assertRaises(ValueError): self.route()
    def test_shared_account_is_not_a_fallback(self):
        self.config['agents'][1]['account'] = 'one'
        self.assertEqual(self.route()['status'], 'parked')
    def test_benched_fallback_parks(self):
        self.ledger['two'] = dict(until=2000)
        self.assertEqual(self.route()['status'], 'parked')
    def test_unapproved_fallback_parks(self):
        self.config['agents'][1]['enabled'] = False
        self.assertEqual(self.route()['status'], 'parked')
    def test_reset_time_wins(self):
        self.event['reset_at'] = '1970-01-01T01:00:00Z'
        self.route()
        self.assertEqual(self.ledger['one']['until'], 3600)
    def test_each_account_once(self):
        self.packet['attempted_accounts'] = ['two']
        self.assertEqual(self.route()['status'], 'parked')

class ParityTests(unittest.TestCase):
    def reports(self): return [copy.deepcopy({'s1': {'status':'passed', 'observations':{'value':2}}}) for _ in range(4)]
    def test_green_equal(self): self.assertEqual(parity.compare(self.reports()), 1)
    def test_equal_red_is_not_success(self):
        reports = self.reports()
        for r in reports: r['s1']['status'] = 'failed'
        with self.assertRaises(ValueError): parity.compare(reports)
    def test_behavior_difference_fails(self):
        reports = self.reports()
        for r in reports[2:]: r['s1']['observations']['value'] = 3
        with self.assertRaises(ValueError): parity.compare(reports)
    def test_nondeterminism_fails(self):
        reports = self.reports(); reports[1]['s1']['observations']['value'] = 4
        with self.assertRaises(ValueError): parity.compare(reports)
    def test_boolean_is_not_numeric_parity(self):
        reports = self.reports()
        for r in reports[:2]: r['s1']['observations']['value'] = True
        for r in reports[2:]: r['s1']['observations']['value'] = 1
        with self.assertRaises(ValueError): parity.compare(reports)
    def test_empty_fails(self):
        with self.assertRaises(ValueError): parity.compare([{}, {}, {}, {}])

class InstallTests(unittest.TestCase):
    def test_conflict_preserves_existing_and_installs_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp); (target/'tdd').mkdir(); (target/'tdd/marker').write_text('keep')
            with self.assertRaises(ValueError): installer.install(ROOT/'skills', target)
            self.assertEqual((target/'tdd/marker').read_text(), 'keep')
            self.assertEqual(len(list(target.iterdir())), 1)
    def test_fresh_install_has_dependencies(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp); self.assertGreater(installer.install(ROOT/'skills', target), 10)
            self.assertTrue((target/'slice-pipeline/scripts/pipeline.py').is_file())

if __name__ == '__main__': unittest.main()
