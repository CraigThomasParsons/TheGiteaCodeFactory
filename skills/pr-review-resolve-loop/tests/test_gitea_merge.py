import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('gitea_merge', Path(__file__).parents[1] / 'scripts/gitea_merge.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class FakeApi:
    def __init__(self):
        self.pr = {'state':'open','draft':False,'merged':False,'mergeable':True,
                   'head':{'sha':'a'*40,'ref':'feature/x','repo':{'full_name':'owner/repo'}},'base':{'sha':'b'*40,'ref':'develop'},'labels':[{'name':'review:clear'}]}
        self.rows = [{'id':2,'context':'test','status':'success'}]
        self.posts = []
        self.gets = 0
        self.change = None
        self.fail_post = False
    def call(self, method, path, body=None):
        if method == 'POST':
            self.posts.append(body)
            if self.fail_post: raise m.Blocked('server refused')
            self.pr['merged'] = True
            self.pr['state'] = 'closed'
            self.pr['merge_commit_sha'] = 'c'*40
            return None
        self.gets += 1
        if self.gets == 2 and self.change: self.change(self.pr)
        return copy.deepcopy(self.pr)
    def statuses(self, prefix, sha): return self.rows

class MergeTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi()
        self.receipt = {'schema_version':1,'server':m.SERVER,'repo':'owner/repo','pr':1,
                        'head_sha':'a'*40,'base_sha':'b'*40,'base_ref':'develop','head_ref':'feature/x','head_repo':'owner/repo','findings':[],
                        'standards_review':'clear','spec_review':'clear','required_contexts':['test']}
    def run_merge(self, execute=True): return m.run(self.api,'owner/repo',1,self.receipt,'squash',execute)
    def blocked(self):
        with self.assertRaises(m.Blocked): self.run_merge()
        self.assertEqual(self.api.posts, [])
    def test_inspect_does_not_mutate(self):
        self.assertEqual(self.run_merge(False)['status'],'eligible')
        self.assertEqual(self.api.posts, [])
    def test_guarded_merge_verified(self):
        self.assertEqual(self.run_merge()['status'],'merged')
        self.assertEqual(self.api.posts,[{'do':'squash','head_commit_id':'a'*40,'force_merge':False,
                                         'delete_branch_after_merge':False,'merge_when_checks_succeed':False}])
    def test_missing_merge_revision_is_not_verified(self):
        original = self.api.call
        def call(method, path, body=None):
            result = original(method, path, body)
            if method == 'POST': self.api.pr.pop('merge_commit_sha', None)
            return result
        self.api.call = call
        with self.assertRaises(m.Blocked): self.run_merge()
        self.assertEqual(len(self.api.posts), 1)
    def test_uncertain_merge_requires_revision(self):
        original = self.api.call
        def call(method, path, body=None):
            result = original(method, path, body)
            if method == 'POST':
                self.api.pr.pop('merge_commit_sha', None)
                raise m.Blocked('reply lost')
            return result
        self.api.call = call
        with self.assertRaises(m.Blocked): self.run_merge()
        self.assertEqual(len(self.api.posts), 1)
    def test_new_head_after_review_blocks(self):
        self.api.change=lambda pr:pr['head'].update(sha='d'*40)
        self.blocked()
    def test_new_base_after_review_blocks(self):
        self.api.change=lambda pr:pr['base'].update(sha='d'*40)
        self.blocked()
    def test_retarget_same_sha_blocks(self):
        self.api.change=lambda pr:pr['base'].update(ref='main')
        self.blocked()
    def test_removed_label_before_merge_blocks(self):
        self.api.change=lambda pr:pr.update(labels=[])
        self.blocked()
    def test_conflicting_findings_blocks(self):
        self.api.pr['labels'].append({'name':'review:findings'})
        self.blocked()
    def test_receipt_wrong_repo_blocks(self):
        self.receipt['repo']='other/repo';self.blocked()
    def test_unresolved_finding_blocks(self):
        self.receipt['findings']=['a problem'];self.blocked()
    def test_missing_checks_blocks(self):
        self.api.rows=[];self.blocked()
    def test_pending_check_blocks(self):
        self.api.rows[0]['status']='pending';self.blocked()
    def test_latest_failed_status_beats_old_success(self):
        self.api.rows.append({'id':3,'context':'test','status':'failure'});self.blocked()
    def test_superseded_failed_status_does_not_block(self):
        self.api.rows.append({'id':1,'context':'test','status':'failure'})
        self.assertEqual(self.run_merge()['status'],'merged')
    def test_draft_blocks(self):
        self.api.pr['draft']=True;self.blocked()
    def test_mergeability_unknown_blocks(self):
        self.api.pr['mergeable']=None;self.blocked()
    def test_refusal_not_retried(self):
        self.api.fail_post=True
        with self.assertRaises(m.Blocked):self.run_merge()
        self.assertEqual(len(self.api.posts),1)

class PaginationTests(unittest.TestCase):
    def test_server_smaller_page_cap_does_not_truncate(self):
        api=object.__new__(m.Api)
        batches=iter([[{'id':1}], [{'id':2}], []])
        api.call=lambda *args:next(batches)
        self.assertEqual(api.statuses('/repos/a/b','sha'),[{'id':1},{'id':2}])

if __name__ == '__main__':unittest.main()
