"""Synthetic Project plan-reference checks, with no real research or model."""
import copy
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

import test_tabular_quality_feedback as fixture
from autoresearch.contracts import ResearchError, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch import tabular_quality_plan


class QualityPlanTests(unittest.TestCase):
    def stage(self, *, met=True):
        f=fixture.QualityFeedbackTests(methodName='runTest');f.setUp();self.addCleanup(f.doCleanups)
        rules=f.valid if met else fixture.rules(fixture.condition('rows','gt',4))
        f.register(reg=rules);f.execute()
        return f

    def plan(self, ref):
        return {'question':'Synthetic quality-linked plan','basis':'Saved profile observation',
                'steps':'Inspect eligible numeric association','expected_feedback':'Retain uncertainty',
                'quality_feedback_ref':ref}

    def fail(self, code, fn, **kwargs):
        with self.assertRaises(ResearchError) as err:fn(**kwargs)
        self.assertEqual(err.exception.code,code)

    def test_known_feedback_creates_direct_successor_and_old_policy_waits(self):
        for met in (True,False):
            with self.subTest(met=met):
                f=self.stage(met=met); before=f.project.status(); db=f.project.db.read_bytes()
                ref=f.project.prepare_tabular_quality_plan_ref(registration_request_id='reg')
                self.assertEqual(f.project.db.read_bytes(),db)
                self.assertEqual(ref['feedback_sha256'],fingerprint(f.project.read_tabular_quality_feedback(request_id='reg')))
                args=dict(request_id='plan2',expected_state_version=before['state_version'],plan=self.plan(ref),reason='Synthetic revision')
                saved=f.project.save_plan(**args);after=f.project.status()
                self.assertEqual(saved['version'],2);self.assertEqual(saved['quality_feedback_ref'],ref)
                self.assertEqual(after['budget'],before['budget']); self.assertEqual(f.project.save_plan(**args),saved)
                self.assertEqual(f.project.status(),after)
                context=ProjectController(f.project.root).selection_context();self.assertEqual(context['research_plan'],saved)
                self.assertEqual(f.project.read_tabular_quality_feedback(request_id='reg')['unknown_reason'],'plan_binding_changed')
                response=ProjectController(f.project.root).advance_tabular_quality_feedback(request_id='branch',registration_request_id='reg',
                    expected_state_version=after['state_version'])
                self.assertEqual(response['status'],'waiting');self.assertEqual(len(f.project.status()['actions']),1)

    def test_unknown_before_action_and_intervening_plan_rejected(self):
        f=fixture.QualityFeedbackTests(methodName='runTest');f.setUp();self.addCleanup(f.doCleanups);f.register()
        self.fail('CONDITION_NOT_SATISFIED',f.project.prepare_tabular_quality_plan_ref,registration_request_id='reg')
        f.execute(); ref=f.project.prepare_tabular_quality_plan_ref(registration_request_id='reg')
        original={'question':'Unrelated','basis':'Synthetic','steps':'Wait','expected_feedback':'None'}
        f.project.save_plan(request_id='other',expected_state_version=f.project.status()['state_version'],plan=original,reason='Synthetic')
        before=f.project.status()
        self.fail('CONDITION_NOT_SATISFIED',f.project.save_plan,request_id='plan2',expected_state_version=before['state_version'],
                  plan=self.plan(ref),reason='Synthetic')
        self.assertEqual(f.project.status(),before)

    def test_reference_and_sql_tampering_fail_closed(self):
        f=self.stage(); ref=f.project.prepare_tabular_quality_plan_ref(registration_request_id='reg');before=f.project.status()
        for key in ('registration_sha256','original_plan_sha256','quality_parent_request_sha256','quality_result_sha256','feedback_sha256','source_snapshot_sha256'):
            with self.subTest(field=key):
                bad={**ref,key:'a'*64}
                self.fail('EVIDENCE_CHANGED',f.project.save_plan,request_id='plan2',expected_state_version=before['state_version'],plan=self.plan(bad),reason='Synthetic')
                self.assertEqual(f.project.status(),before)
        child=before['actions'][0]['request_id']
        with sqlite3.connect(f.project.db) as con:con.execute('update actions set fingerprint=? where request_id=?',('a'*64,child))
        self.fail('CONDITION_NOT_SATISFIED',f.project.save_plan,request_id='plan2',expected_state_version=before['state_version'],plan=self.plan(ref),reason='Synthetic')

    def test_same_id_replay_rechecks_source_and_identity(self):
        f=self.stage();ref=f.project.prepare_tabular_quality_plan_ref(registration_request_id='reg')
        args=dict(request_id='plan2',expected_state_version=f.project.status()['state_version'],plan=self.plan(ref),reason='Synthetic')
        f.project.save_plan(**args);before=f.project.status();source=f.project.root/'source.json';original=source.read_bytes()
        source.write_bytes(original+b' ')
        self.fail('CONDITION_NOT_SATISFIED',f.project.save_plan,**args)
        source.write_bytes(original);self.assertEqual(f.project.status(),before)
        changed={**args,'plan':{**args['plan'],'quality_feedback_ref':{**ref,'feedback_sha256':'a'*64}}}
        self.fail('IDEMPOTENCY_CONFLICT',f.project.save_plan,**changed)

    def test_manager_rejects_before_intent(self):
        f=self.stage();ref=f.project.prepare_tabular_quality_plan_ref(registration_request_id='reg')
        manager=LocalWorkbench(f.root/'manager');pid=f.project.status()['id'];manager.import_project(request_id='import',workspace=f.project.root)
        manager.select({'request_id':'select','project_id':pid});project,_=manager.binding()
        body={'request_id':'plan2','project_id':pid,'expected_state_version':project.status()['state_version'],
              'plan':self.plan(ref),'reason':'Synthetic'}
        db=manager.db.read_bytes();self.fail('INVALID_REQUEST',manager.save_plan,body=body);self.assertEqual(manager.db.read_bytes(),db)

    def test_bad_shape_cross_project_and_result_bytes(self):
        f=self.stage();ref=f.project.prepare_tabular_quality_plan_ref(registration_request_id='reg');state=f.project.status()
        for bad in ({**ref,'original_plan_version':True}, {**ref,'extra':'not allowed'},
                    {key:value for key,value in ref.items() if key!='quality_action_id'}):
            with self.subTest(bad=bad):
                self.fail('INVALID_REQUEST',f.project.save_plan,request_id='plan2',expected_state_version=state['state_version'],
                          plan=self.plan(bad),reason='Synthetic')
        other=self.stage();other_before=other.project.status()
        self.fail('EVIDENCE_CHANGED',other.project.save_plan,request_id='plan2',expected_state_version=other_before['state_version'],
                  plan=self.plan(ref),reason='Synthetic')
        self.assertEqual(other.project.status(),other_before)
        artifact=f.project.root/state['actions'][0]['artifact'];original=artifact.read_bytes();artifact.write_bytes(original+b' ')
        self.fail('CONDITION_NOT_SATISFIED',f.project.save_plan,request_id='plan2',expected_state_version=state['state_version'],
                  plan=self.plan(ref),reason='Synthetic')
        artifact.write_bytes(original);self.assertEqual(f.project.status(),state)

    def test_producer_code_drift_stops_save_and_replay(self):
        f=self.stage();ref=f.project.prepare_tabular_quality_plan_ref(registration_request_id='reg')
        args={'request_id':'plan2','expected_state_version':f.project.status()['state_version'],'plan':self.plan(ref),'reason':'Synthetic'}
        original=Path.read_bytes;path=Path(tabular_quality_plan.__file__).resolve()
        def drift(p):
            raw=original(p)
            return raw+b'\n# synthetic drift' if p.resolve()==path else raw
        with patch.object(Path,'read_bytes',drift):
            self.fail('CODE_CHANGED',f.project.save_plan,**args)
        f.project.save_plan(**args);state=f.project.status()
        with patch.object(Path,'read_bytes',drift):
            self.fail('CONDITION_NOT_SATISFIED',f.project.save_plan,**args)
        self.assertEqual(f.project.status(),state)

    def test_code_drift_after_saved_feedback_stops_reference_and_plan(self):
        f=self.stage();ref=f.project.prepare_tabular_quality_plan_ref(registration_request_id='reg')
        args={'request_id':'plan2','expected_state_version':f.project.status()['state_version'],'plan':self.plan(ref),'reason':'Synthetic'}
        original_outcome=tabular_quality_plan.feedback._outcome;original_read=Path.read_bytes
        for module in (tabular_quality_plan, tabular_quality_plan.feedback, __import__('autoresearch.project_controller',fromlist=['x'])):
            with self.subTest(module=module.__name__):
                changed=[False]; target=Path(module.__file__).resolve()
                def outcome(*a,**k):
                    result=original_outcome(*a,**k);changed[0]=True;return result
                def drift(p):
                    raw=original_read(p)
                    return raw+b'\n# synthetic drift' if changed[0] and p.resolve()==target else raw
                with patch.object(tabular_quality_plan.feedback,'_outcome',side_effect=outcome),patch.object(Path,'read_bytes',drift):
                    self.fail('CODE_CHANGED',f.project.save_plan,**args)
                self.assertEqual(len(f.project.status()['plan_revisions']),1)


if __name__=='__main__':unittest.main()
