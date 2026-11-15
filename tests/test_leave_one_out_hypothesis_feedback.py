"""Preregistered leave-one-out policy; independently generated synthetic inputs."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_staged_relevance_adapter as fixtures
import test_hypothesis_feedback as legacy_fixtures
from autoresearch import (hypothesis_feedback as feedback, feedback_policy, staged_feedback_reader as reader,
                          staged_relevance_adapter as staged, retrieval_holdout as holdout, project_selection)
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class LeaveOneOutFeedbackTests(unittest.TestCase):
    def fixture(self, *, n=3, mean_operator='gte', loo_operator='gte', loo_threshold=0, execute=True, loo_metric='recall@20'):
        helper=fixtures.StagedDevelopmentTests();helper.setUp();self.addCleanup(helper.doCleanups)
        queries=[{'_id':'qd','text':'cat','metadata':{}},{'_id':'qv','text':'unknown token','metadata':{}}]
        qrels='query-id\tcorpus-id\tscore\nqd\ta\t2\nqv\tb\t1\n'
        if n==3:
            queries += [{'_id':'q2','text':'neverpresentone','metadata':{}},{'_id':'q3','text':'neverpresenttwo','metadata':{}}]
            qrels+='q2\tc\t1\nq3\ta\t1\n'
            helper.spec['query_splits']['validation']=['qv','q2','q3']
        (helper.root/'queries.jsonl').write_text(fixtures._rows(queries))
        (helper.root/'qrels.tsv').write_text(qrels);helper.write_spec()
        packet=helper.capture();tmp=self.enterContext(tempfile.TemporaryDirectory());root=Path(tmp)
        (root/'input').mkdir();source=root/'input/source.json';source.write_text(canonical(packet))
        original=ResearchProject(root/'original')
        original.create(source=source,goal='Synthetic LOO engineering only',budget_ref='fixture',max_tool_calls=3,method_id=staged.TOOL_ID)
        original.save_plan(request_id='plan',expected_state_version=original.status()['state_version'],
            plan={'question':'Fixture?', 'basis':'Synthetic only', 'steps':'Check fixed pair', 'expected_feedback':'Saved metrics'},reason='Fixture')
        manager=LocalWorkbench(root/'manager');imported=manager.import_project(request_id='import',workspace=original.root)
        project_id=imported['project_id'];manager.select({'request_id':'select','project_id':project_id});project,_=manager.binding()
        private={'schema_version':'retrieval-holdout-v1','corpus_sha256':packet['assets']['corpus']['sha256'],
                 'queries_jsonl':canonical({'_id':'final-q','text':'SECRET_FINAL fish','metadata':{}})+'\n',
                 'qrels_tsv':'query-id\tcorpus-id\tscore\nfinal-q\tc\t1\n'}
        manager.register_holdout({'request_id':'holdout','project_id':project_id,'expected_state_version':project.status()['state_version'],
             'holdout_base64':base64.b64encode(canonical(private).encode()).decode()})
        controller=ProjectController(project.root);ctx=controller.selection_context()
        candidate=next(c for c in ctx['candidates'] if c['method_id']==staged.TOOL_ID)
        hypothesis={'candidate_id':candidate['id'],'controller_request_id':'future',
            'conditions':[{'metric':'recall@20','operator':mean_operator,'threshold':0},
                          {'metric':'mrr@10','operator':'gte','threshold':0}],
            'leave_one_out':{'metric':loo_metric,'operator':loo_operator,'threshold':loo_threshold},
            'branches':{'condition_met':{'kind':'method','method_id':staged.AUDIT_TOOL_ID},'condition_not_met':{'kind':'wait'}}}
        version=ctx['state_version'];record=project.register_hypothesis(request_id='prediction',expected_state_version=version,hypothesis=hypothesis)
        if execute:
            ctx=controller.selection_context();proposal={'schema_version':'project-selection-proposal-v1',
                'context_sha256':ctx['context_sha256'],'provider':{'kind':'human','label':'Synthetic engineering'},
                'choice':{'kind':'execute','candidate_id':candidate['id']},'rationale':'Original preregistered fixture',
                'evidence_citation_ids':[]}
            controller.advance_selection(request_id='future',expected_state_version=ctx['state_version'],proposal=proposal)
        return manager,project,record,hypothesis,version

    def test_zero_strict_operators_and_single_primary_check(self):
        for operator,expected in [('gt','condition_not_met'),('gte','condition_met'),('lt','condition_not_met'),('lte','condition_met')]:
            with self.subTest(operator=operator):
                _,project,record,_,_=self.fixture(loo_operator=operator)
                with patch.object(reader,'_checked_primary',wraps=reader._checked_primary) as checked:
                    context=feedback.feedback_context(project,project.status());self.assertEqual(checked.call_count,1)
                item=context['items'][0];self.assertEqual(context['schema_version'],'hypothesis-feedback-context-v3')
                self.assertEqual(record['schema_version'],'hypothesis-registration-v3')
                self.assertEqual(item['outcome'],expected);self.assertEqual(item['value']['means'],[0,0])
                self.assertEqual(item['value']['leave_one_out'],{'minimum':0,'maximum':0,'queries':3})
                self.assertEqual(feedback.validate_context(context),context)
                self.assertNotIn('SECRET_FINAL',canonical(context))

    def test_unknown_precedes_failed_mean_and_all_partial_values_suppressed(self):
        _,project,_,_,_=self.fixture(n=1,mean_operator='gt')
        state=project.status();item=feedback.feedback_context(project,state)['items'][0]
        self.assertEqual((item['outcome'],item['unknown_reason'],item['value']),('unknown','insufficient_validation_queries',None))
        for bad in ({'means':[0,True],'leave_one_out':{'minimum':0,'maximum':0,'queries':3}},
                    {'means':[0,0],'leave_one_out':{'minimum':float('nan'),'maximum':0,'queries':3}},
                    {'means':[0,0],'leave_one_out':{'minimum':0,'maximum':0,'queries':True}},
                    {'means':[0,None],'leave_one_out':{'minimum':0,'maximum':0,'queries':3}}):
            with self.subTest(bad=bad),patch.object(reader,'read_validation_deltas_and_loo',return_value=bad):
                observed=feedback.feedback_context(project,state)['items'][0]
                self.assertEqual((observed['outcome'],observed['value'],observed['action_id'],observed['result_sha256']),('unknown',None,None,None))
        self.assertEqual(project.status(),state)

    def test_saved_mean_strict_and_loo_extrema_not_epsilon_rounded(self):
        _,project,_,_,_=self.fixture(mean_operator='gt',loo_operator='gt')
        state=project.status()
        value={'means':[0,0],'leave_one_out':{'minimum':5e-16,'maximum':5e-16,'queries':3}}
        with patch.object(reader,'read_validation_deltas_and_loo',return_value=value):
            self.assertEqual(feedback.feedback_context(project,state)['items'][0]['outcome'],'condition_not_met')
        _,project,_,_,_=self.fixture(loo_operator='gt');state=project.status()
        with patch.object(reader,'read_validation_deltas_and_loo',return_value=value):
            self.assertEqual(feedback.feedback_context(project,state)['items'][0]['outcome'],'condition_met')

    def test_all_five_metric_loo_and_exact_registration_replay(self):
        _,project,record,hypothesis,version=self.fixture()
        state=project.status();action=state['actions'][0]
        for metric in ('recall@5','recall@10','recall@20','mrr@10','ndcg@10'):
            other='mrr@10' if metric!='mrr@10' else 'recall@20'
            with patch.object(reader,'_checked_primary',wraps=reader._checked_primary) as checked:
                value=reader.read_validation_deltas_and_loo(project,state,action,[metric,other],metric)
                self.assertEqual(checked.call_count,1);self.assertEqual(value['leave_one_out']['queries'],3)
        self.assertEqual(ResearchProject(project.root).register_hypothesis(request_id='prediction',expected_state_version=version,hypothesis=hypothesis),record)
        changed=copy.deepcopy(hypothesis);changed['leave_one_out']['threshold']=.1
        with self.assertRaises(ResearchError) as error:
            project.register_hypothesis(request_id='prediction',expected_state_version=version,hypothesis=changed)
        self.assertEqual(error.exception.code,'IDEMPOTENCY_CONFLICT')

    def test_checked_reader_preserves_saved_mean_not_fsum_near_zero(self):
        metrics = {}
        for qid, candidate in [('q1',1e-15), ('q2',0)]:
            for method, score in [('bm25',0), ('tfidf_cosine',candidate)]:
                metrics[('validation',qid,method)]={'metrics':{'recall@20':score}}
        checked={'source':{'spec':{'query_splits':{'validation':['q1','q2']}}},'metrics':metrics,
                 'summary':{'splits':{'validation':{'paired_candidate_minus_baseline':{
                     'recall@20':{'mean':0,'wins':0,'losses':0,'ties':2},
                     'mrr@10':{'mean':0,'wins':0,'losses':0,'ties':2}}}}}}
        with patch.object(reader,'_checked_primary',return_value=checked) as called:
            value=reader.read_validation_deltas_and_loo(None,None,None,['recall@20','mrr@10'],'recall@20')
        self.assertEqual(called.call_count,1);self.assertEqual(value['means'],[0,0])
        self.assertEqual(value['leave_one_out']['minimum'],0)
        self.assertEqual(value['leave_one_out']['maximum'],1e-15)
        condition={'all':[{'metric':'recall@20','operator':'gt','threshold':0},
                          {'metric':'mrr@10','operator':'gte','threshold':0}],
                   'leave_one_out':{'metric':'recall@20','operator':'gte','threshold':0}}
        self.assertFalse(feedback._loo_matches(condition,value))

    def test_mixed_v1_v2_v3_items_keep_original_conditions(self):
        _,project,record,_,_=self.fixture(execute=False)
        context=ProjectController(project.root).selection_context()
        candidate=next(c for c in context['candidates'] if c['method_id']==staged.TOOL_ID)
        v1={'candidate_id':candidate['id'],'controller_request_id':'future-v1','metric':'recall@20','operator':'gte','threshold':0}
        first=project.register_hypothesis(request_id='prediction-v1',expected_state_version=context['state_version'],hypothesis=v1)
        context=ProjectController(project.root).selection_context()
        v2={'candidate_id':candidate['id'],'controller_request_id':'future-v2',
            'conditions':[{'metric':'recall@20','operator':'gte','threshold':0},{'metric':'mrr@10','operator':'gte','threshold':0}]}
        second=project.register_hypothesis(request_id='prediction-v2',expected_state_version=context['state_version'],hypothesis=v2)
        output=feedback.feedback_context(project,project.status());items={x['request_id']:x for x in output['items']}
        self.assertEqual(output['schema_version'],'hypothesis-feedback-context-v3')
        for key,registered in [('prediction',record),('prediction-v1',first),('prediction-v2',second)]:
            self.assertEqual(items[key]['condition'],registered['condition']);self.assertEqual(items[key]['outcome'],'unknown')
        self.assertEqual(feedback.validate_context(output),output)

    def test_insufficient_validation_count_waits_on_original_s052(self):
        manager,project,_,_,_=self.fixture(n=1,mean_operator='gt');state=project.status()
        body={'request_id':'continue','project_id':state['id'],'expected_state_version':state['state_version'],
              'primary_action_id':state['actions'][0]['id'],'reason':'Synthetic original unknown route',
              'registration_request_id':'prediction'}
        result=manager.continue_staged(body)
        self.assertEqual((result['phase'],result['conditional']['feedback']['outcome']),('waiting','unknown'))
        self.assertEqual(result['conditional']['feedback']['unknown_reason'],'insufficient_validation_queries')
        self.assertEqual(manager.continue_staged(body),result);self.assertEqual(project.status(),state)

    def test_s052_wait_and_audit_use_original_overall_outcome(self):
        for op,phase,count in [('gt','waiting',1),('gte','done',3)]:
            with self.subTest(op=op):
                manager,project,_,_,_=self.fixture(loo_operator=op);state=project.status()
                body={'request_id':'continue','project_id':state['id'],'expected_state_version':state['state_version'],
                     'primary_action_id':state['actions'][0]['id'],'reason':'Synthetic original conditional route',
                     'registration_request_id':'prediction'}
                result=manager.continue_staged(body);self.assertEqual(result['phase'],phase)
                self.assertEqual(manager.continue_staged(body),result)
                self.assertEqual(project.status()['budget']['local_tool_calls_used'],count)
                self.assertEqual((project.status()['budget']['new_model_requests'],project.status()['budget']['new_fits']),(0,0))
                if phase=='waiting':self.assertEqual(project.status(),state)
                else:self.assertEqual([a['command'] for a in project.status()['actions']],[staged.TOOL_ID,staged.AUDIT_TOOL_ID,holdout.FINAL_TOOL_ID])

    def test_invalid_registration_context_and_tampered_artifact(self):
        _,project,record,hypothesis,_=self.fixture();state=project.status()
        for key,value in (('metric','ndcg@10'),('metric','test/recall@20'),('operator','eq'),('threshold',True),('threshold',float('nan'))):
            bad=copy.deepcopy(hypothesis);bad['controller_request_id']='new-future';bad['leave_one_out'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ResearchError):
                project.register_hypothesis(request_id='bad',expected_state_version=state['state_version'],hypothesis=bad)
        ctx=feedback.feedback_context(project,state)
        for key,value in (('queries',True),('queries',1),('minimum',True),('maximum',float('inf'))):
            bad=copy.deepcopy(ctx);bad['items'][0]['value']['leave_one_out'][key]=value
            with self.subTest(key=key),self.assertRaises(ResearchError):feedback.validate_context(bad)
        changed=copy.deepcopy(ctx);changed['items'][0]['condition']['leave_one_out']['threshold']=True
        with self.assertRaises(ResearchError):feedback.validate_context(changed)
        envpath=project._artifact(state['actions'][0]);raw=envpath.read_bytes()
        try:
            env=json.loads(raw);env['tool_result']['result']['rankings'][0]['query_line']+=1;envpath.write_text(canonical(env))
            self.assertEqual(feedback.feedback_context(project,project.status())['items'][0]['outcome'],'unknown')
        finally:envpath.write_bytes(raw)
        self.assertEqual(project.status(),state)

    def test_resealed_context_cannot_change_validation_coverage(self):
        _,project,record,_,_=self.fixture()
        context=ProjectController(project.root).selection_context()
        changed=copy.deepcopy(context);changed.pop('context_sha256')
        changed['hypothesis_feedback']['items'][0]['value']['leave_one_out']['queries']=4
        with self.assertRaises(ResearchError):project_selection.seal_context(changed)
        changed['domain_scope']['query_split_counts']['validation']=4
        resealed=project_selection.seal_context(changed)
        proposal=feedback_policy.select_from_feedback(resealed,registration=record,provider={'kind':'human','label':'Fixture'})
        self.assertEqual(proposal['choice']['kind'],'wait')
        broken=copy.deepcopy(record);broken.pop('scope_sha256')
        broken['registration_sha256']=fingerprint({k:v for k,v in broken.items() if k!='registration_sha256'})
        with self.assertRaises(ResearchError):
            feedback_policy.select_from_feedback(context,registration=broken,provider={'kind':'human','label':'Fixture'})

    def test_v3_resealed_condition_does_not_bypass_frozen_policy(self):
        _,project,record,_,_=self.fixture()
        ctx=ProjectController(project.root).selection_context();provider={'kind':'human','label':'Synthetic'}
        self.assertEqual(feedback_policy.select_from_feedback(ctx,registration=record,provider=provider)['choice']['kind'],'execute')
        changed=copy.deepcopy(ctx);changed['hypothesis_feedback']['items'][0]['condition']['leave_one_out']['threshold']=0.0
        changed.pop('context_sha256');changed=project_selection.seal_context(changed)
        self.assertEqual(feedback_policy.select_from_feedback(changed,registration=record,provider=provider)['choice']['kind'],'wait')

    def test_legacy_family_rejects_v3(self):
        helper=legacy_fixtures.HypothesisFeedbackTests();self.addCleanup(helper.doCleanups)
        project,candidate=helper.fixture();before=project.status()
        h={'candidate_id':candidate['id'],'controller_request_id':'future',
           'conditions':[{'metric':'recall@20','operator':'gt','threshold':0},{'metric':'mrr@10','operator':'gte','threshold':0}],
           'leave_one_out':{'metric':'recall@20','operator':'gte','threshold':0}}
        with self.assertRaises(ResearchError):project.register_hypothesis(request_id='prediction',expected_state_version=before['state_version'],hypothesis=h)
        self.assertEqual(project.status(),before)
