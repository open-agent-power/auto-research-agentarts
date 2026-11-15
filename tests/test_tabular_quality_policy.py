"""Synthetic quality-policy selection, terminal replay and process race tests."""
import copy
import json
import multiprocessing
import sqlite3
from unittest.mock import patch
import unittest

from autoresearch import numeric_association_adapter as numeric, project_selection
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
from tests import test_tabular_quality_feedback as fixture
condition, rules = fixture.condition, fixture.rules


def _worker(root, body, entered, proceed, out, stall):
    controller=ProjectController(root)
    original=ProjectController._dispatch
    def gated(self,parent,*,replayed):
        if stall:
            entered.set()
            if not proceed.wait(15): raise RuntimeError('synthetic timeout')
        return original(self,parent,replayed=replayed)
    try:
        with patch.object(ProjectController,'_dispatch',gated):
            result=controller.advance_tabular_quality_feedback(**body)
        out.put(('ok',result['status'],result['replayed']))
    except Exception as exc:
        out.put(('error',getattr(exc,'code',type(exc).__name__),str(exc)))


class QualityPolicyTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.QualityFeedbackTests(methodName='runTest');self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.p,self.c=self.f.project,self.f.controller

    def body(self, request='next'):
        return {'request_id':request,'registration_request_id':'reg','expected_state_version':self.p.status()['state_version']}

    def ready(self, reg=None):
        self.f.register(reg=reg);self.f.execute()

    def test_met_dispatch_and_terminal_replay_no_dispatch(self):
        self.ready();body=self.body();r=self.c.advance_tabular_quality_feedback(**body)
        self.assertEqual(r['status'],'completed');state=self.p.status()
        self.assertEqual([a['command'] for a in state['actions']],['data.tabular-quality-audit','data.numeric-association'])
        self.assertEqual((state['budget']['local_tool_calls_used'],state['budget']['new_fits'],
                          state['budget']['new_model_requests'],state['budget']['evidence_reads_used']),(2,0,0,0))
        parent=next(p for p in state['controller_requests'] if p['request_id']=='next')
        self.assertEqual(parent['tabular_quality_policy']['feedback']['outcome'],'condition_met')
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('replay dispatched')), \
             patch.object(ResearchProject,'step',side_effect=AssertionError('replay stepped')), \
             patch.object(numeric,'execute',side_effect=AssertionError('replay executed')):
            replay=self.c.advance_tabular_quality_feedback(**body)
        self.assertTrue(replay['replayed']);self.assertEqual(replay['result'],r['result']);self.assertEqual(self.p.status(),state)
        # This opt-in parent cannot be resumed through the legacy direct entry.
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('direct replay dispatched')):
            with self.assertRaises(ResearchError) as err:
                self.c.advance_selection(request_id='next',proposal=parent['request']['proposal'],
                                         expected_state_version=body['expected_state_version'])
        self.assertEqual(err.exception.code,'IDEMPOTENCY_CONFLICT')
        changed={**body,'expected_state_version':body['expected_state_version']+1}
        with self.assertRaises(ResearchError) as err:self.c.advance_tabular_quality_feedback(**changed)
        self.assertEqual(err.exception.code,'IDEMPOTENCY_CONFLICT')

    def test_known_false_and_unstarted_wait_without_tool(self):
        self.ready(reg=rules(condition('rows','gt',4)))
        before=self.p.status();r=self.c.advance_tabular_quality_feedback(**self.body())
        self.assertEqual(r['status'],'waiting');self.assertEqual(self.p.status()['budget']['local_tool_calls_used'],1)
        self.assertEqual(len(self.p.status()['actions']),len(before['actions']))

    def test_unstarted_unknown_waits_without_action(self):
        self.f.register();r=self.c.advance_tabular_quality_feedback(**self.body())
        self.assertEqual(r['status'],'waiting');self.assertEqual(self.p.status()['budget']['local_tool_calls_used'],0)

    def test_plan_change_is_unknown_and_waits(self):
        self.ready();state=self.p.status()
        self.p.save_plan(request_id='newplan',expected_state_version=state['state_version'],
            plan={'question':'Changed','basis':'Synthetic','steps':'Wait','expected_feedback':'Unknown'},reason='Synthetic')
        body=self.body();r=self.c.advance_tabular_quality_feedback(**body);self.assertEqual(r['status'],'waiting')
        self.assertEqual(self.p.status()['budget']['local_tool_calls_used'],1)
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('replay dispatched')):
            replay=self.c.advance_tabular_quality_feedback(**body)
        self.assertTrue(replay['replayed']);self.assertEqual(replay['status'],'waiting')

    def test_no_or_ambiguous_candidate_and_wrong_cost_wait(self):
        self.ready();original=self.c._selection_context
        for kind in ('missing','ambiguous','cost'):
            with self.subTest(kind=kind):
                def altered(state,need):
                    ctx=original(state,need);payload={k:copy.deepcopy(v) for k,v in ctx.items() if k!='context_sha256'}
                    candidates=[c for c in payload['candidates'] if c['method_id']==numeric.TOOL_ID]
                    self.assertEqual(len(candidates),1)
                    if kind=='missing':payload['candidates'].remove(candidates[0])
                    elif kind=='ambiguous':
                        duplicate=copy.deepcopy(candidates[0]);duplicate['id']='choice-synthetic-ambiguous';payload['candidates'].append(duplicate)
                    else:next(v for v in payload['conditions'] if v['method_id']==numeric.TOOL_ID)['budget_cost']['evidence_reads']=1
                    return project_selection.seal_context(payload)
                with patch.object(self.c,'_selection_context',side_effect=altered):
                    response=self.c.advance_tabular_quality_feedback(**self.body('wait-'+kind))
                self.assertEqual(response['status'],'waiting')
                self.assertEqual(self.p.status()['budget']['local_tool_calls_used'],1)

    def test_exhausted_synthetic_budget_waits(self):
        source=self.f.root/'capture/input.json';p=ResearchProject(self.f.root/'one-tool-project')
        state=p.create(source=source,goal='Synthetic exhausted allowance',budget_ref='fixture:one',max_tool_calls=1,
                       method_id='data.tabular-quality-audit')
        p.limit_evidence_budget(request_id='zero2',expected_limit=8,new_limit=0,
                                expected_state_version=state['state_version'],reason='Synthetic')
        plan={'question':'Synthetic','basis':'Artificial','steps':'Quality','expected_feedback':'Wait'}
        p.save_plan(request_id='plan2',expected_state_version=p.status()['state_version'],plan=plan,reason='Synthetic')
        c=ProjectController(p.root);ctx=c.selection_context();candidate=next(v for v in ctx['candidates'] if v['method_id']=='data.tabular-quality-audit')
        p.register_tabular_quality_conditions(request_id='reg2',expected_state_version=ctx['state_version'],
            controller_request_id='q2',candidate_id=candidate['id'],conditions=rules(condition('rows','eq',4)))
        ctx=c.selection_context();proposal={'schema_version':'project-selection-proposal-v1','context_sha256':ctx['context_sha256'],
            'provider':{'kind':'human','label':'synthetic'},'choice':{'kind':'execute','candidate_id':candidate['id']},
            'rationale':'Synthetic','evidence_citation_ids':[]}
        c.advance_selection(request_id='q2',proposal=proposal,expected_state_version=ctx['state_version'])
        body={'request_id':'next2','registration_request_id':'reg2','expected_state_version':p.status()['state_version']}
        with patch.object(ResearchProject,'step',side_effect=AssertionError('budget-exhausted dispatch')):
            result=c.advance_tabular_quality_feedback(**body)
        self.assertEqual(result['status'],'waiting');self.assertEqual(p.status()['budget']['local_tool_calls_used'],1)

    def test_source_drift_waits_and_no_action_dispatched(self):
        self.ready();path=self.p.root/'source.json';raw=path.read_bytes();path.write_bytes(raw+b' ')
        with patch.object(ResearchProject,'step',side_effect=AssertionError('source-drift dispatch')):
            result=self.c.advance_tabular_quality_feedback(**self.body())
        self.assertEqual(result['status'],'waiting');self.assertEqual(self.p.status()['budget']['local_tool_calls_used'],1)

    def test_accepted_nonterminal_never_reissued_through_either_entry(self):
        self.ready();body=self.body()
        with patch.object(ProjectController,'_dispatch',side_effect=RuntimeError('synthetic cut after parent accepted')):
            with self.assertRaises(RuntimeError):self.c.advance_tabular_quality_feedback(**body)
        state=self.p.status();parent=next(p for p in state['controller_requests'] if p['request_id']=='next')
        self.assertEqual(parent['status'],'prepared');before=self.p.db.read_bytes()
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('replay dispatched')), \
             patch.object(ResearchProject,'step',side_effect=AssertionError('replay stepped')):
            with self.assertRaises(ResearchError) as err:self.c.advance_tabular_quality_feedback(**body)
            self.assertEqual(err.exception.code,'EXECUTION_UNKNOWN')
            with self.assertRaises(ResearchError) as err:
                self.c.advance_selection(request_id='next',proposal=parent['request']['proposal'],
                                         expected_state_version=body['expected_state_version'])
            self.assertEqual(err.exception.code,'IDEMPOTENCY_CONFLICT')
            with self.assertRaises(ResearchError) as err:self.c.advance_tabular_quality_feedback(**self.body('other'))
            self.assertEqual(err.exception.code,'EXECUTION_UNKNOWN')
        self.assertEqual(self.p.db.read_bytes(),before);self.assertEqual(self.p.status(),state)

    def test_existing_running_unknown_and_completed_child_parent_do_not_replay(self):
        self.ready();body=self.body();self.c.advance_tabular_quality_feedback(**body)
        for status in ('prepared','running','unknown'):
            with self.subTest(status=status):
                with sqlite3.connect(self.p.db) as con:
                    project=json.loads(con.execute('select record from project').fetchone()[0])
                    parent=next(p for p in project['controller_requests'] if p['request_id']=='next')
                    parent['status']=status;con.execute('update project set record=? where id=1',(canonical(project),))
                before=self.p.db.read_bytes()
                with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('replay dispatched')), \
                     patch.object(ResearchProject,'step',side_effect=AssertionError('replay stepped')):
                    with self.assertRaises(ResearchError) as err:self.c.advance_tabular_quality_feedback(**body)
                self.assertEqual(err.exception.code,'EXECUTION_UNKNOWN');self.assertEqual(self.p.db.read_bytes(),before)

    def test_child_running_or_unknown_cannot_be_resumed(self):
        self.ready();body=self.body();self.c.advance_tabular_quality_feedback(**body)
        child_id=self.p.status()['actions'][1]['request_id']
        for status in ('running','unknown'):
            with self.subTest(status=status):
                with sqlite3.connect(self.p.db) as con:
                    project=json.loads(con.execute('select record from project').fetchone()[0])
                    parent=next(p for p in project['controller_requests'] if p['request_id']=='next')
                    parent['status']='running';parent['result']=None
                    con.execute('update project set record=? where id=1',(canonical(project),))
                    action=json.loads(con.execute('select record from actions where request_id=?',(child_id,)).fetchone()[0])
                    action['status']=status;con.execute('update actions set record=? where request_id=?',(canonical(action),child_id))
                before=self.p.db.read_bytes()
                with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('replay dispatched')), \
                     patch.object(ResearchProject,'step',side_effect=AssertionError('replay stepped')):
                    with self.assertRaises(ResearchError) as err:self.c.advance_tabular_quality_feedback(**body)
                self.assertEqual(err.exception.code,'EXECUTION_UNKNOWN');self.assertEqual(self.p.db.read_bytes(),before)

    def test_standard_report_reads_policy_selection_without_project_mutation(self):
        from autoresearch.project_report import collect_report
        self.ready();self.c.advance_tabular_quality_feedback(**self.body());before=self.p.status()
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('report dispatched')):
            report=collect_report(self.p.root)
        self.assertEqual(report['project_snapshot_ref'],before['snapshot_ref'])
        self.assertEqual(self.p.status(),before)
        self.assertEqual(len(report['selection_history']['records']),2)

    def test_terminal_replay_allows_later_plan_but_checks_original_quality(self):
        self.ready();body=self.body();self.c.advance_tabular_quality_feedback(**body)
        state=self.p.status()
        self.p.save_plan(request_id='later-plan',expected_state_version=state['state_version'],
            plan={'question':'Later synthetic','basis':'After action','steps':'Wait','expected_feedback':'None'},reason='Synthetic')
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('replay dispatched')):
            self.assertTrue(self.c.advance_tabular_quality_feedback(**body)['replayed'])
        quality=self.p.status()['actions'][0]
        with sqlite3.connect(self.p.db) as con:
            con.execute('update actions set fingerprint=? where request_id=?',('a'*64,quality['request_id']))
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('replay dispatched')):
            with self.assertRaises(ResearchError) as err:self.c.advance_tabular_quality_feedback(**body)
        self.assertEqual(err.exception.code,'EVIDENCE_CHANGED')

    def test_terminal_child_coordinated_request_forgery_is_rejected(self):
        self.ready();body=self.body();self.c.advance_tabular_quality_feedback(**body)
        state=self.p.status();child=state['actions'][1];artifact=self.p.root/child['artifact']
        envelope=json.loads(artifact.read_bytes());envelope['request_sha256']='e'*64
        envelope['sha256']=fixture.fingerprint({k:v for k,v in envelope.items() if k!='sha256'})
        artifact.write_text(canonical(envelope))
        with sqlite3.connect(self.p.db) as con:
            childrow=json.loads(con.execute('select record from actions where request_id=?',(child['request_id'],)).fetchone()[0])
            childrow['request_sha256']='e'*64;childrow['result_sha256']=envelope['sha256']
            con.execute('update actions set fingerprint=?,record=? where request_id=?',('e'*64,canonical(childrow),child['request_id']))
            project=json.loads(con.execute('select record from project where id=1').fetchone()[0])
            parent=next(p for p in project['controller_requests'] if p['request_id']=='next')
            parent['result']['child']['result_sha256']=envelope['sha256']
            con.execute('update project set record=? where id=1',(canonical(project),))
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('replay dispatched')):
            with self.assertRaises(ResearchError) as err:self.c.advance_tabular_quality_feedback(**body)
        self.assertEqual(err.exception.code,'EVIDENCE_CHANGED')

    def test_rejected_before_child_replays_original_error_without_dispatch(self):
        self.ready();body=self.body();before=self.p.status()['budget']['local_tool_calls_used']
        with patch.object(ResearchProject,'step',side_effect=ResearchError('BUDGET_EXHAUSTED','synthetic original refusal')):
            with self.assertRaises(ResearchError) as first:self.c.advance_tabular_quality_feedback(**body)
        self.assertEqual((first.exception.code,str(first.exception)),('BUDGET_EXHAUSTED','synthetic original refusal'))
        state=self.p.status();parent=next(p for p in state['controller_requests'] if p['request_id']=='next')
        self.assertEqual(parent['status'],'rejected');self.assertIsNone(parent['result']['child'])
        self.assertEqual(state['budget']['local_tool_calls_used'],before)
        self.assertFalse(any(a['request_id']==parent['child_request_id'] for a in state['actions']))
        database=self.p.db.read_bytes()
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('replay dispatched')), \
             patch.object(ResearchProject,'step',side_effect=AssertionError('replay stepped')):
            with self.assertRaises(ResearchError) as replay:self.c.advance_tabular_quality_feedback(**body)
        self.assertEqual((replay.exception.code,str(replay.exception)),('BUDGET_EXHAUSTED','synthetic original refusal'))
        self.assertEqual(self.p.db.read_bytes(),database);self.assertEqual(self.p.status(),state)
        with self.assertRaises(ResearchError) as changed:
            self.c.advance_tabular_quality_feedback(**{**body,'expected_state_version':body['expected_state_version']+1})
        self.assertEqual(changed.exception.code,'IDEMPOTENCY_CONFLICT')
        # Even a terminal rejection cannot replay its stored error after the
        # original quality predecessor's SQLite identity has drifted.
        quality_id=state['actions'][0]['request_id']
        with sqlite3.connect(self.p.db) as con:
            con.execute('update actions set fingerprint=? where request_id=?',('e'*64,quality_id))
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('replay dispatched')):
            with self.assertRaises(ResearchError) as drift:self.c.advance_tabular_quality_feedback(**body)
        self.assertEqual(drift.exception.code,'EVIDENCE_CHANGED')
        self.assertEqual(self.p.status()['budget']['local_tool_calls_used'],before)

    def test_rejected_parent_with_orphan_replay_stops_without_dispatch(self):
        self.ready();body=self.body()
        with patch.object(ResearchProject,'step',side_effect=ResearchError('BUDGET_EXHAUSTED','synthetic original refusal')):
            with self.assertRaises(ResearchError):self.c.advance_tabular_quality_feedback(**body)
        state=self.p.status();parent=next(p for p in state['controller_requests'] if p['request_id']=='next')
        child_id=parent['child_request_id'];self.assertEqual(state['budget']['local_tool_calls_used'],1)
        for rid,target in ((child_id,'missing-action'),('orphan-alias',child_id)):
            with self.subTest(request_id=rid):
                with sqlite3.connect(self.p.db) as con:con.execute('insert into replays values(?,?)',(rid,target))
                before=self.p.db.read_bytes()
                with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('replay dispatched')), \
                     patch.object(ResearchProject,'step',side_effect=AssertionError('replay stepped')):
                    with self.assertRaises(ResearchError) as err:self.c.advance_tabular_quality_feedback(**body)
                self.assertEqual(err.exception.code,'EVIDENCE_CHANGED');self.assertEqual(self.p.db.read_bytes(),before)
                self.assertEqual(self.p.status()['budget']['local_tool_calls_used'],1)
                with sqlite3.connect(self.p.db) as con:con.execute('delete from replays where request_id=?',(rid,))

    def test_failed_action_terminal_replay_does_not_execute(self):
        self.ready();body=self.body()
        with patch.object(numeric,'execute',side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(ResearchError):self.c.advance_tabular_quality_feedback(**body)
        self.assertEqual(self.p.status()['actions'][-1]['status'],'failed')
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('replay dispatched')):
            replay=self.c.advance_tabular_quality_feedback(**body)
        self.assertTrue(replay['replayed']);self.assertEqual(replay['status'],'failed')

    def test_two_process_same_id_only_original_dispatches(self):
        self.ready();body=self.body();ctx=multiprocessing.get_context('spawn')
        entered,proceed,out=ctx.Event(),ctx.Event(),ctx.Queue()
        first=ctx.Process(target=_worker,args=(str(self.p.root),body,entered,proceed,out,True));first.start()
        self.assertTrue(entered.wait(15),'first did not save prepared parent')
        second=ctx.Process(target=_worker,args=(str(self.p.root),body,entered,proceed,out,False));second.start()
        second.join(15);self.assertEqual(second.exitcode,0)
        rejected=out.get(timeout=5);self.assertEqual(rejected[:2],('error','EXECUTION_UNKNOWN'))
        proceed.set();first.join(15);self.assertEqual(first.exitcode,0)
        self.assertEqual(out.get(timeout=5),('ok','completed',False))
        self.assertEqual(self.p.status()['budget']['local_tool_calls_used'],2)

if __name__=='__main__':unittest.main()
