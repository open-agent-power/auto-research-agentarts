"""Synthetic only: explicit quality policy after a verified successor plan."""
import copy
import json
import multiprocessing
import sqlite3
import unittest
from unittest.mock import patch

import test_tabular_quality_feedback as fixture
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
from autoresearch import project_selection, numeric_association_adapter


def worker(root, body, entered, proceed, results, stall):
    original=ProjectController._dispatch
    def gated(self,parent,*,replayed):
        if stall:
            entered.set()
            if not proceed.wait(15):raise RuntimeError('synthetic timeout')
        return original(self,parent,replayed=replayed)
    try:
        with patch.object(ProjectController,'_dispatch',gated):
            value=ProjectController(root).advance_tabular_quality_feedback_v2(**body)
        results.put(('ok',value['status']))
    except Exception as exc:results.put(('error',getattr(exc,'code',type(exc).__name__)))


class QualityPolicyV2Tests(unittest.TestCase):
    def stage(self, met=True):
        f=fixture.QualityFeedbackTests(methodName='runTest');f.setUp();self.addCleanup(f.doCleanups)
        f.register(reg=f.valid if met else fixture.rules(fixture.condition('rows','gt',4)));f.execute()
        ref=f.project.prepare_tabular_quality_plan_ref(registration_request_id='reg')
        plan={'question':'Synthetic v2','basis':'Quality profile','steps':'Follow exact evidence',
              'expected_feedback':'Retain uncertainty','quality_feedback_ref':ref}
        saved=f.project.save_plan(request_id='plan2',expected_state_version=f.project.status()['state_version'],plan=plan,reason='Synthetic')
        return f,saved

    def body(self,f,plan,request_id='next'):
        return {'request_id':request_id,'registration_request_id':'reg','plan_request_id':plan['request_id'],
                'plan_sha256':fingerprint(plan),'expected_state_version':f.project.status()['state_version']}

    def error(self, code, fn, **kwargs):
        with self.assertRaises(ResearchError) as err:fn(**kwargs)
        self.assertEqual(err.exception.code,code)

    def test_met_dispatch_and_replay_uses_original_context_after_later_plan(self):
        f,plan=self.stage();body=self.body(f,plan);result=f.controller.advance_tabular_quality_feedback_v2(**body)
        self.assertEqual(result['status'],'completed');state=f.project.status();self.assertEqual(len(state['actions']),2)
        self.assertEqual((state['budget']['local_tool_calls_used'],state['budget']['new_model_requests'],
                          state['budget']['new_fits'],state['budget']['evidence_reads_used']),(2,0,0,0))
        parent=next(p for p in state['controller_requests'] if p['request_id']=='next')
        self.assertEqual(parent['selection_context']['research_plan'],plan)
        self.assertEqual(parent['tabular_quality_policy']['schema_version'],'tabular-quality-policy-v2')
        later={'question':'Later','basis':'Synthetic','steps':'Wait','expected_feedback':'None'}
        f.project.save_plan(request_id='plan3',expected_state_version=state['state_version'],plan=later,reason='Synthetic')
        before=f.project.status()
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('redispatch')),patch.object(ResearchProject,'step',side_effect=AssertionError('step')):
            replay=f.controller.advance_tabular_quality_feedback_v2(**body)
        self.assertTrue(replay['replayed']);self.assertEqual(replay['result'],result['result']);self.assertEqual(f.project.status(),before)
        self.error('IDEMPOTENCY_CONFLICT',f.controller.advance_tabular_quality_feedback_v2,**{**body,'plan_sha256':'a'*64})

    def test_not_met_waits_and_original_v1_stays_unknown(self):
        f,plan=self.stage(met=False);before=f.project.status();self.assertEqual(f.project.read_tabular_quality_feedback(request_id='reg')['unknown_reason'],'plan_binding_changed')
        with patch.object(ResearchProject,'step',side_effect=AssertionError('step')):
            result=f.controller.advance_tabular_quality_feedback_v2(**self.body(f,plan))
        self.assertEqual(result['status'],'waiting');self.assertEqual(len(f.project.status()['actions']),1)
        self.assertEqual(f.project.status()['budget'],before['budget'])

    def test_old_or_wrong_plan_rejected_without_parent(self):
        f,plan=self.stage();body=self.body(f,plan)
        self.error('CONDITION_NOT_SATISFIED',f.controller.advance_tabular_quality_feedback_v2,**{**body,'plan_sha256':'a'*64})
        later={'question':'Later','basis':'Synthetic','steps':'Wait','expected_feedback':'None'}
        f.project.save_plan(request_id='plan3',expected_state_version=f.project.status()['state_version'],plan=later,reason='Synthetic')
        self.error('CONDITION_NOT_SATISFIED',f.controller.advance_tabular_quality_feedback_v2,
                   **{**body,'expected_state_version':f.project.status()['state_version']})
        self.assertFalse(any(p['request_id']=='next' for p in f.project.status()['controller_requests']))

    def test_quality_sql_or_artifact_drift_prevents_action(self):
        for kind in ('sql','artifact'):
            with self.subTest(kind=kind):
                f,plan=self.stage();body=self.body(f,plan);state=f.project.status();action=state['actions'][0]
                if kind=='sql':
                    with sqlite3.connect(f.project.db) as con:con.execute('update actions set fingerprint=? where request_id=?',('a'*64,action['request_id']))
                else:
                    path=f.project.root/action['artifact'];path.write_bytes(path.read_bytes()+b' ')
                with patch.object(ResearchProject,'step',side_effect=AssertionError('step')):
                    self.error('CONDITION_NOT_SATISFIED',f.controller.advance_tabular_quality_feedback_v2,**body)
                self.assertEqual(len(f.project.status()['actions']),1)

    def test_nonterminal_parent_never_redispatches(self):
        f,plan=self.stage();body=self.body(f,plan)
        with patch.object(ProjectController,'_dispatch',side_effect=RuntimeError('synthetic interruption')):
            with self.assertRaises(RuntimeError):f.controller.advance_tabular_quality_feedback_v2(**body)
        before=f.project.db.read_bytes()
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('redispatch')):
            self.error('EXECUTION_UNKNOWN',f.controller.advance_tabular_quality_feedback_v2,**body)
            self.error('EXECUTION_UNKNOWN',f.controller.advance_tabular_quality_feedback_v2,**self.body(f,plan,'other'))
        self.assertEqual(f.project.db.read_bytes(),before)

    def test_two_process_same_id_only_original_dispatches(self):
        f,plan=self.stage();body=self.body(f,plan);ctx=multiprocessing.get_context('fork')
        entered=ctx.Event();proceed=ctx.Event();results=ctx.Queue()
        first=ctx.Process(target=worker,args=(f.project.root,body,entered,proceed,results,True));first.start()
        self.assertTrue(entered.wait(15))
        second=ctx.Process(target=worker,args=(f.project.root,body,entered,proceed,results,False));second.start();second.join(15)
        self.assertFalse(second.is_alive());self.assertEqual(results.get(timeout=5),('error','EXECUTION_UNKNOWN'))
        proceed.set();first.join(15);self.assertFalse(first.is_alive());self.assertEqual(results.get(timeout=5),('ok','completed'))
        self.assertEqual(len(f.project.status()['actions']),2)

    def test_replay_reauthenticates_quality_and_child_sql(self):
        for index in (0,1):
            with self.subTest(index=index):
                f,plan=self.stage();body=self.body(f,plan);f.controller.advance_tabular_quality_feedback_v2(**body)
                action=f.project.status()['actions'][index]
                with sqlite3.connect(f.project.db) as con:con.execute('update actions set fingerprint=? where request_id=?',('a'*64,action['request_id']))
                with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('redispatch')):
                    with self.assertRaises(ResearchError):f.controller.advance_tabular_quality_feedback_v2(**body)

    def test_source_or_code_drift_cannot_dispatch(self):
        from pathlib import Path
        from autoresearch import tabular_quality_plan
        for kind in ('source','code'):
            with self.subTest(kind=kind):
                f,plan=self.stage();body=self.body(f,plan)
                if kind=='source':
                    path=f.project.root/'source.json';path.write_bytes(path.read_bytes()+b' ')
                    with patch.object(ResearchProject,'step',side_effect=AssertionError('step')):
                        self.error('CONDITION_NOT_SATISFIED',f.controller.advance_tabular_quality_feedback_v2,**body)
                else:
                    target=Path(tabular_quality_plan.__file__).resolve();read=Path.read_bytes
                    def drift(p):
                        raw=read(p);return raw+b'\n# synthetic drift' if p.resolve()==target else raw
                    with patch.object(Path,'read_bytes',drift),patch.object(ResearchProject,'step',side_effect=AssertionError('step')):
                        self.error('CODE_CHANGED',f.controller.advance_tabular_quality_feedback_v2,**body)
                self.assertEqual(len(f.project.status()['actions']),1)

    def test_budget_exhaustion_and_ambiguous_candidate_wait(self):
        create=ResearchProject.create
        def one_tool(project,*args,**kwargs):
            kwargs['max_tool_calls']=1
            return create(project,*args,**kwargs)
        with patch.object(ResearchProject,'create',new=one_tool):f,plan=self.stage()
        with patch.object(ResearchProject,'step',side_effect=AssertionError('budget dispatch')):
            self.assertEqual(f.controller.advance_tabular_quality_feedback_v2(**self.body(f,plan))['status'],'waiting')
        self.assertEqual(f.project.status()['budget']['local_tool_calls_used'],1)
        f,plan=self.stage(); original=f.controller._selection_context
        def ambiguous(state,need):
            ctx=original(state,need);payload={k:copy.deepcopy(v) for k,v in ctx.items() if k!='context_sha256'}
            original_candidate=next(c for c in payload['candidates'] if c['method_id']==numeric_association_adapter.TOOL_ID)
            duplicate=copy.deepcopy(original_candidate);duplicate['id']='choice-synthetic-ambiguous'
            payload['candidates'].append(duplicate)
            return project_selection.seal_context(payload)
        with patch.object(f.controller,'_selection_context',side_effect=ambiguous),patch.object(ResearchProject,'step',side_effect=AssertionError('ambiguous dispatch')):
            self.assertEqual(f.controller.advance_tabular_quality_feedback_v2(**self.body(f,plan))['status'],'waiting')
        self.assertEqual(f.project.status()['budget']['local_tool_calls_used'],1)

    def test_v1_v2_and_selection_cannot_cross_replay(self):
        f,plan=self.stage();body=self.body(f,plan);f.controller.advance_tabular_quality_feedback_v2(**body)
        parent=next(p for p in f.project.status()['controller_requests'] if p['request_id']=='next')
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('cross replay')):
            self.error('IDEMPOTENCY_CONFLICT',f.controller.advance_tabular_quality_feedback,
                       request_id='next',registration_request_id='reg',expected_state_version=body['expected_state_version'])
            self.error('IDEMPOTENCY_CONFLICT',f.controller.advance_selection,request_id='next',
                       proposal=parent['request']['proposal'],expected_state_version=body['expected_state_version'])
        f,plan=self.stage();body=self.body(f,plan)
        f.controller.advance_tabular_quality_feedback(request_id='next',registration_request_id='reg',expected_state_version=body['expected_state_version'])
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('cross replay')):
            self.error('IDEMPOTENCY_CONFLICT',f.controller.advance_tabular_quality_feedback_v2,**body)

    def test_running_and_unknown_parent_remain_stopped(self):
        f,plan=self.stage();body=self.body(f,plan);f.controller.advance_tabular_quality_feedback_v2(**body)
        for status in ('prepared','running','unknown'):
            with self.subTest(status=status):
                with sqlite3.connect(f.project.db) as con:
                    state=json.loads(con.execute('select record from project where id=1').fetchone()[0])
                    next(p for p in state['controller_requests'] if p['request_id']=='next')['status']=status
                    con.execute('update project set record=? where id=1',(canonical(state),))
                before=f.project.db.read_bytes()
                with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('redispatch')):
                    self.error('EXECUTION_UNKNOWN',f.controller.advance_tabular_quality_feedback_v2,**body)
                self.assertEqual(f.project.db.read_bytes(),before)

    def test_quality_sql_change_during_decision_or_replay_is_rejected(self):
        for replay in (False, True):
            with self.subTest(replay=replay):
                f,plan=self.stage();body=self.body(f,plan)
                if replay:f.controller.advance_tabular_quality_feedback_v2(**body)
                action=f.project.status()['actions'][0];original=f.controller._selected_plan
                def drift(*args,**kwargs):
                    result=original(*args,**kwargs)
                    with sqlite3.connect(f.project.db) as con:
                        con.execute('update actions set fingerprint=? where request_id=?',('a'*64,action['request_id']))
                    return result
                with patch.object(f.controller,'_selected_plan',side_effect=drift),patch.object(ResearchProject,'step',side_effect=AssertionError('dispatch')):
                    with self.assertRaises(ResearchError):f.controller.advance_tabular_quality_feedback_v2(**body)
                self.assertEqual(len(f.project.status()['actions']),2 if replay else 1)
                if not replay:self.assertFalse(any(p['request_id']=='next' for p in f.project.status()['controller_requests']))

    def test_original_rejection_replays_without_child(self):
        f,plan=self.stage();body=self.body(f,plan);failure=ResearchError('SYNTHETIC_REJECTED','Synthetic failure')
        with patch.object(ResearchProject,'step',side_effect=failure):
            self.error('SYNTHETIC_REJECTED',f.controller.advance_tabular_quality_feedback_v2,**body)
        before=f.project.status();self.assertEqual(len(before['actions']),1)
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('redispatch')):
            self.error('SYNTHETIC_REJECTED',f.controller.advance_tabular_quality_feedback_v2,**body)
        self.assertEqual(f.project.status(),before)

    def test_orphan_replay_references_parent_or_child_fail_closed(self):
        for target_kind in ('parent','child'):
            with self.subTest(target_kind=target_kind):
                f,plan=self.stage();body=self.body(f,plan);state=f.project.status()
                target='next' if target_kind=='parent' else 'controller-child-'+fingerprint({'project_id':state['id'],'request_id':'next'})[:32]
                with sqlite3.connect(f.project.db) as con:con.execute('insert into replays values(?,?)',('orphan-alias',target))
                before=f.project.db.read_bytes()
                with patch.object(ResearchProject,'step',side_effect=AssertionError('dispatch')):
                    self.error('IDEMPOTENCY_CONFLICT',f.controller.advance_tabular_quality_feedback_v2,**body)
                self.assertEqual(f.project.db.read_bytes(),before)


if __name__=='__main__':unittest.main()
