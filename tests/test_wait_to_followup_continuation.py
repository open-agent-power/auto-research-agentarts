"""Independent synthetic Project: a saved unknown wait followed by an explicit decision.

These tests create their own source and budget. They do not load a prior research
case. The replay subprocess hashes complete synthetic manager trees, including
synthetic private holdout/report bytes, to check byte identity.
"""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

import test_staged_relevance_adapter as fixture
from autoresearch import hypothesis_feedback, staged_relevance_adapter as staged
from autoresearch.contracts import ResearchError, canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
from autoresearch.staged_wait_experience import StagedWaitExperienceMemory, derive_wait_observation


CHILD = r'''
import hashlib,json,sys
from pathlib import Path
from autoresearch import hypothesis_feedback
from autoresearch.contracts import ResearchError,canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController

def snapshot(root):
    values={}
    for path in sorted(root.rglob('*')):
        if path.is_symlink(): raise AssertionError('redirected path')
        if path.is_file():
            raw=path.read_bytes();values[str(path.relative_to(root))]=hashlib.sha256(raw).hexdigest()
    return values

arg=json.loads(sys.stdin.read());manager=LocalWorkbench(arg['manager']); project,_=manager.binding()
before=project.status()
if arg['phase']=='execute':
    context=ProjectController(project.root).selection_context()
    assert context['context_sha256']==arg['primary']['proposal']['context_sha256']
    assert context['experience']['cases'][0]['observation']['feedback']['outcome']=='unknown'
    assert context['research_plan']==arg['plan']
    result=ProjectController(project.root).advance_selection(**arg['primary'])
    state=project.status(); action=state['actions'][0]
    parent=next(x for x in state['controller_requests'] if x['request_id']=='primary')
    assert parent['request']['proposal']['experience_case_refs']==[arg['case_ref']]
    assert parent['selection_context']['research_plan']==arg['plan']
    item=hypothesis_feedback.feedback_context(project,state)['items'][0]
    assert item['outcome']=='condition_met' and item['action_id']==action['id']
    assert item['result_sha256']==action['result_sha256'] and item['registration_sha256']==arg['registration_sha']
    body={'request_id':'later-conditional','project_id':state['id'],'expected_state_version':state['state_version'],
          'primary_action_id':action['id'],'reason':'Explicit later synthetic decision.', 'registration_request_id':'prediction'}
    path=Path(arg['case_root'])/'later-body.json'
    with path.open('x') as out:out.write(canonical(body))
    later=manager.continue_staged(body)
    state=project.status()
    assert state['budget']['new_model_requests']==0 and state['budget']['new_fits']==0
    assert len(state['actions'])==(3 if arg['limit']==3 else 1)
    if arg['limit']==3:
        assert later['phase']=='done' and len(state['actions'])==3
    else:
        assert later['phase']=='waiting' and later['conditional']['feedback']['outcome']=='condition_met'
        assert 'audit candidate is unavailable or ambiguous' in later['conditional']['proposal']['rationale']
        assert later['steps']=={} and later['result']['final_evaluation_performed'] is False
        try:
            project.freeze_retrieval_strategy(request_id='bad-freeze',expected_state_version=state['state_version'],primary_action_id=action['id'])
        except ResearchError as error:assert error.code=='CONDITION_NOT_SATISFIED'
        else:raise AssertionError('missing audit cannot authorize freeze')
    print(canonical({'primary':result,'later':later,'feedback':item,'snapshot_ref':state['snapshot_ref'],
                     'budget':state['budget'],'count':len(state['actions'])}))
else:
    initial=snapshot(manager.root)
    wait=manager.continue_staged(arg['wait_body']); assert canonical(wait)==canonical(arg['wait_receipt'])
    if arg['phase']=='replay':
        primary=ProjectController(project.root).advance_selection(**arg['primary']);assert primary['replayed']
        later=manager.continue_staged(arg['later_body']);assert canonical(later)==canonical(arg['later'])
    else:
        item=hypothesis_feedback.feedback_context(project,before)['items'][0]
        assert item['outcome']=='unknown' and item['unknown_reason']=='controller_not_started'
        assert all(item[k] is None for k in ('value','action_id','result_sha256'))
        assert not before['actions'] and before['budget']['local_tool_calls_used']==0
    assert snapshot(manager.root)==initial and project.status()==before
    print(canonical({'snapshot_ref':before['snapshot_ref'],'count':len(before['actions']),'budget':before['budget'],
                     'managed_file_count':len(initial),'files_and_state_unchanged':True}))
'''


class WaitToFollowupTests(unittest.TestCase):
    @staticmethod
    def card():
        return {'schema_version':'research-method-card-v1','id':'wait-fixture','version':1,
                'question':'What remains unknown?','rationale':'Synthetic waiting case.',
                'scope_match':{'domain':'retrieval','contract':staged.CONTRACT},
                'method_refs':[{'method_id':staged.TOOL_ID,'evaluation_ref':'staged-relevance-development-v1'}],
                'applicability':{'requires':['Verify source.'],'not_applicable':['No general result.'],'uncertain':['Synthetic only.']},
                'evaluation':'Original validation feedback.',
                'feedback_branches':[{'id':'wait','observed':'A wait.','suggested_next':'Inspect conditions.',
                                      'evidence_required':['Original receipt.']}],
                'sources':[{'id':'source','url':'urn:test:synthetic','locator':'fixture','note':'Synthetic only.'}]}

    def make_source(self, limit):
        helper=fixture.StagedDevelopmentTests();helper.setUp();self.addCleanup(helper.doCleanups)
        rng=random.Random(108); words=['amber','blue','cyan','denim','ecru']
        docs=[{'_id':str(i),'title':'','text':' '.join(w for w in words for _ in range(rng.randint(0,5))),'metadata':{}} for i in range(40)]
        (helper.root/'corpus.jsonl').write_text(fixture._rows(docs))
        (helper.root/'queries.jsonl').write_text(fixture._rows([{'_id':'qd','text':'amber','metadata':{}},
                                                                {'_id':'qv','text':'amber blue cyan','metadata':{}}]))
        (helper.root/'qrels.tsv').write_text('query-id\tcorpus-id\tscore\nqd\t1\t1\nqv\t1\t1\n')
        helper.write_spec(); packet=helper.capture()
        root=Path(self.enterContext(tempfile.TemporaryDirectory()))
        (root/'input').mkdir();source=root/'input'/'source.json';source.write_text(canonical(packet))
        original=ResearchProject(root/'original');original.create(source=source,goal='Synthetic wait to explicit decision',
                    budget_ref='engineering-fixture',max_tool_calls=limit,method_id=staged.TOOL_ID)
        original.save_plan(request_id='plan',expected_state_version=original.status()['state_version'],
                           plan={'question':'Fixture?','basis':'Synthetic','steps':'Fixed pair',
                                 'expected_feedback':'Validation feedback'},reason='Synthetic')
        manager=LocalWorkbench(root/'manager');pid=manager.import_project(request_id='import',workspace=original.root)['project_id']
        manager.select({'request_id':'select','project_id':pid});project,_=manager.binding()
        private={'schema_version':'retrieval-holdout-v1','corpus_sha256':packet['assets']['corpus']['sha256'],
                 'queries_jsonl':canonical({'_id':'final-q','text':'SECRET_FINAL amber','metadata':{}})+'\n',
                 'qrels_tsv':'query-id\tcorpus-id\tscore\nfinal-q\t1\t1\n'}
        policy={'kind':'registered_feedback','registration_request_id':'prediction','condition_met':'tfidf_cosine',
                'condition_not_met':'bm25','unknown':'stop'}
        manager.register_holdout({'request_id':'holdout','project_id':pid,'expected_state_version':project.status()['state_version'],
                     'holdout_base64':base64.b64encode(canonical(private).encode()).decode(),'selection_policy':policy})
        context=ProjectController(project.root).selection_context()
        candidate=next(c for c in context['candidates'] if c['method_id']==staged.TOOL_ID)
        reg=project.register_hypothesis(request_id='prediction',expected_state_version=context['state_version'],hypothesis={
            'candidate_id':candidate['id'],'controller_request_id':'primary','metric':'recall@20','operator':'gte','threshold':0,
            'branches':{'condition_met':{'kind':'method','method_id':staged.AUDIT_TOOL_ID},'condition_not_met':{'kind':'wait'}}})
        state=project.status()
        wait_body={'request_id':'first-wait','project_id':pid,'expected_state_version':state['state_version'],
                   'primary_action_id':'future-primary-action','reason':'Wait before synthetic primary.',
                   'registration_request_id':'prediction'}
        wait=manager.continue_staged(wait_body)
        self.assertEqual(wait['conditional']['feedback']['unknown_reason'],'controller_not_started')
        self.assertEqual(project.status(),state)
        memory=StagedWaitExperienceMemory(root/'memory'); receipt=memory.import_wait(manager.root,'first-wait')
        entry=memory.recall(receipt['scope'])['entries'][0]['record']
        bundle=memory.export_case(receipt['scope'],entry['id'],case_id='earlier-wait',version=1,
                                  method_card=self.card(),limitations=['Synthetic only.'])
        state=project.status()
        case_body={'request_id':'case-import','project_id':pid,'expected_state_version':state['state_version'],
                   'bundle_base64':base64.b64encode(canonical(bundle).encode()).decode(),
                   'reason':'Review the earlier unknown at the next explicit decision.'}
        self.assertFalse(manager.import_experience(case_body)['replayed'])
        self.assertTrue(manager.import_experience(case_body)['replayed'])
        state=project.status();context=ProjectController(project.root).selection_context()
        case=context['experience']['cases'][0];ref={k:case[k] for k in ('case_id','case_version','bundle_sha256')}
        proposal={'schema_version':'project-selection-proposal-v1','context_sha256':context['context_sha256'],
                  'provider':{'kind':'human','label':'Synthetic engineering operator'},
                  'choice':{'kind':'execute','candidate_id':reg['candidate']['id']},
                  'rationale':'Explicitly execute the original preregistered primary.','evidence_citation_ids':[],
                  'experience_case_refs':[ref]}
        primary={'request_id':'primary','expected_state_version':state['state_version'],'proposal':proposal}
        return root,manager,project,{'manager':str(manager.root),'case_root':str(root),'limit':limit,
                    'primary':primary,'plan':copy.deepcopy(context['research_plan']),'case_ref':ref,
                    'registration_sha':reg['registration_sha256'],'wait_body':wait_body,'wait_receipt':wait}

    def child(self, values):
        result=subprocess.run([sys.executable,'-B','-c',CHILD], input=canonical(values),text=True,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=os.environ.copy(),timeout=90)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout)

    def test_explicit_followup_replays_in_new_process(self):
        root,manager,project,arg=self.make_source(3)
        before=project.status();self.assertEqual(before['budget']['local_tool_calls_used'],0)
        original=self.child({**arg,'phase':'execute'})
        self.assertEqual(original['feedback']['outcome'],'condition_met')
        self.assertEqual(original['later']['phase'],'done'); self.assertEqual(original['count'],3)
        later_body=json.loads((root/'later-body.json').read_text())
        replay=self.child({**arg,'phase':'replay','later_body':later_body,'later':original['later']})
        self.assertEqual(replay['snapshot_ref'],original['snapshot_ref'])
        self.assertEqual(replay['budget'],original['budget']);self.assertTrue(replay['files_and_state_unchanged'])

    def test_exhausted_budget_waits_without_freeze_or_new_dispatch(self):
        root,manager,project,arg=self.make_source(1)
        original=self.child({**arg,'phase':'execute'})
        self.assertEqual(original['later']['phase'],'waiting');self.assertEqual(original['count'],1)
        self.assertEqual(original['budget']['local_tool_calls_used'],1)
        replay=self.child({**arg,'phase':'replay','later_body':json.loads((root/'later-body.json').read_text()),'later':original['later']})
        self.assertEqual(replay['budget'],original['budget']);self.assertTrue(replay['files_and_state_unchanged'])

    def test_unknown_wait_stays_unknown_and_stale_capture_refuses(self):
        _,manager,project,arg=self.make_source(3)
        before=project.status()
        replay=self.child({**arg,'phase':'unknown'})
        self.assertEqual(replay['count'],0);self.assertTrue(replay['files_and_state_unchanged'])
        with self.assertRaises(ResearchError) as caught:derive_wait_observation(manager.root,'first-wait')
        self.assertEqual(caught.exception.code,'EVIDENCE_CHANGED');self.assertEqual(project.status(),before)


if __name__=='__main__':unittest.main()
