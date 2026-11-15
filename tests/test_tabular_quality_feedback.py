"""Isolated synthetic registration/reader tests. No model or real research."""
import copy
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_numeric_association as fixtures
from autoresearch import hypothesis_feedback, tabular_quality_adapter as tabular
from autoresearch import tabular_quality_conditions as quality_conditions
from autoresearch import tabular_quality_feedback as feedback
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


def condition(field, op='eq', value=0, column=None):
    value = {'field':field, 'operator':op, 'value':value}
    if column is not None: value['column']=column
    return value


def rules(*items):
    return {'schema_version':'tabular-quality-conditions-v1','conditions':list(items)}


class QualityFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory(prefix='quality-feedback-synthetic-')))
        f=fixtures.NumericAssociationTests(methodName='runTest');self.addCleanup(f.doCleanups)
        packet=f.payload('group,x,outcome\na,1,2\na,2,4\nb,3,6\nb,4,8\n')
        (self.root/'capture').mkdir();source=self.root/'capture/input.json';source.write_text(canonical(packet))
        self.project=ResearchProject(self.root/'project')
        state=self.project.create(source=source,goal='Synthetic quality feedback',budget_ref='fixture:only',
                                  max_tool_calls=2,method_id=tabular.TOOL_ID)
        self.project.limit_evidence_budget(request_id='zero',expected_limit=8,new_limit=0,
                                          expected_state_version=state['state_version'],reason='Synthetic no evidence')
        plan={'question':'Synthetic question','basis':'Artificial records only',
              'steps':'Test bounded quality conditions','expected_feedback':'Unknown stays unknown'}
        self.project.save_plan(request_id='plan',expected_state_version=self.project.status()['state_version'],
                               plan=plan,reason='Synthetic plan')
        self.controller=ProjectController(self.project.root)
        context=self.controller.selection_context()
        self.candidate=next(c for c in context['candidates'] if c['method_id']==tabular.TOOL_ID)
        self.original_context=context
        self.valid=rules(condition('rows','eq',4),condition('numeric.finite','eq',{'ref':'rows'},column='x'),
                         {'field':'flags','operator':'empty'})

    def register(self, *, req='reg', target='quality', reg=None):
        return self.project.register_tabular_quality_conditions(request_id=req,expected_state_version=self.project.status()['state_version'],
            controller_request_id=target,candidate_id=self.candidate['id'],conditions=self.valid if reg is None else reg)

    def execute(self,target='quality'):
        ctx=self.controller.selection_context()
        proposal={'schema_version':'project-selection-proposal-v1','context_sha256':ctx['context_sha256'],
                  'provider':{'kind':'human','label':'synthetic'},'choice':{'kind':'execute','candidate_id':self.candidate['id']},
                  'rationale':'Only synthetic data.','evidence_citation_ids':[]}
        return self.controller.advance_selection(request_id=target,proposal=proposal,expected_state_version=ctx['state_version'])

    def mutate_project(self,fn):
        with sqlite3.connect(self.project.db) as con:
            p=json.loads(con.execute('select record from project where id=1').fetchone()[0]);fn(p)
            con.execute('update project set record=? where id=1',(canonical(p),))

    def test_opt_in_met_same_id_and_read_only(self):
        initial=self.project.status();self.assertNotIn('tabular_quality_registrations',initial)
        rec=self.register();after_register=self.project.status()
        self.assertNotEqual(self.original_context['context_sha256'],self.controller.selection_context()['context_sha256'])
        replay=self.project.register_tabular_quality_conditions(**rec['request']);self.assertEqual(rec,replay)
        self.assertEqual(self.project.status(),after_register)
        self.assertEqual(self.project.read_tabular_quality_feedback(request_id='reg')['unknown_reason'],'controller_not_started')
        response=self.execute();self.assertEqual(response['status'],'completed')
        before=self.project.status();database=self.project.db.read_bytes()
        with patch.object(tabular,'execute',side_effect=AssertionError('reader dispatched')), \
             patch.object(ResearchProject,'step',side_effect=AssertionError('reader dispatched')), \
             patch.object(ResearchProject,'read_evidence',side_effect=AssertionError('reader used evidence')):
            output=self.project.read_tabular_quality_feedback(request_id='reg')
        self.assertEqual(output['outcome'],'condition_met');self.assertIs(output['scientific_validation'],False)
        self.assertEqual(output['action_id'],before['actions'][0]['id'])
        self.assertEqual(output['result_sha256'],before['actions'][0]['result_sha256'])
        self.assertEqual(before,self.project.status());self.assertEqual(database,self.project.db.read_bytes())
        budget=before['budget'];self.assertEqual((budget['local_tool_calls_used'],budget['new_model_requests'],
            budget['new_fits'],budget['evidence_reads_used'],budget['evidence_read_limit']),(1,0,0,0,0))

    def test_known_false_and_unknown_outcomes(self):
        self.register(reg=rules(condition('rows','gt',4),condition('group.group_count','eq',2)))
        self.execute();result=self.project.read_tabular_quality_feedback(request_id='reg')
        self.assertEqual(result['outcome'],'condition_not_met')
        # In-memory evaluator tests unknown precedence; corrupt saved values cannot
        # be substituted without invalidating the original artifact binding.
        self.assertIsNone(result['unknown_reason'])

    def test_reject_late_registration_and_same_id_body_change(self):
        record=self.register()
        with self.assertRaises(ResearchError) as error:
            self.project.register_tabular_quality_conditions(**{**record['request'],'conditions':rules(condition('rows','eq',5))})
        self.assertEqual(error.exception.code,'IDEMPOTENCY_CONFLICT')
        self.execute()
        with self.assertRaises(ResearchError) as error:self.register(req='late',target='later')
        self.assertEqual(error.exception.code,'CONDITION_NOT_SATISFIED')

    def test_plan_change_and_other_command_claim_unknown(self):
        self.register();state=self.project.status()
        plan={'question':'Changed plan','basis':'Synthetic','steps':'Wait','expected_feedback':'Unknown'}
        self.project.save_plan(request_id='quality',expected_state_version=state['state_version'],plan=plan,reason='Claim target ID')
        self.assertEqual(self.project.read_tabular_quality_feedback(request_id='reg')['unknown_reason'],'plan_binding_changed')

    def test_source_artifact_and_sql_fingerprint_corruption_unknown(self):
        self.register();self.execute();state=self.project.status();action=state['actions'][0]
        source=self.project.root/'source.json';original=source.read_bytes();source.write_bytes(original+b' ')
        self.assertEqual(self.project.read_tabular_quality_feedback(request_id='reg')['outcome'],'unknown');source.write_bytes(original)
        artifact=self.project.root/action['artifact'];original=artifact.read_bytes();artifact.write_bytes(original+b' ')
        self.assertEqual(self.project.read_tabular_quality_feedback(request_id='reg')['outcome'],'unknown');artifact.write_bytes(original)
        with sqlite3.connect(self.project.db) as con:
            con.execute('update actions set fingerprint=? where request_id=?',('a'*64,action['request_id']))
        self.assertEqual(self.project.read_tabular_quality_feedback(request_id='reg')['unknown_reason'],'child_binding_changed')

    def test_sql_fingerprint_change_during_read_is_unknown(self):
        self.register();self.execute();child=self.project.status()['actions'][0]['request_id']
        original=quality_conditions.evaluate_conditions
        def mutate(*args,**kwargs):
            result=original(*args,**kwargs)
            with sqlite3.connect(self.project.db) as con:
                con.execute('update actions set fingerprint=? where request_id=?',('e'*64,child))
            return result
        with patch.object(quality_conditions,'evaluate_conditions',side_effect=mutate):
            self.assertEqual(self.project.read_tabular_quality_feedback(request_id='reg')['unknown_reason'],'child_changed_during_read')

    def test_dependency_code_drift_fails_closed(self):
        self.register();self.execute()
        original=Path.read_bytes
        for module in (feedback.contract_module,feedback.source_reader,feedback.tabular,quality_conditions):
            path=Path(module.__file__).resolve()
            def drift(p):
                raw=original(p)
                return raw+b'\n# synthetic drift' if p.resolve()==path else raw
            with self.subTest(module=module.__name__),patch.object(Path,'read_bytes',drift):
                self.assertEqual(self.project.read_tabular_quality_feedback(request_id='reg')['outcome'],'unknown')

    def test_actual_unknown_has_precedence_over_known_false(self):
        helper=fixtures.NumericAssociationTests(methodName='runTest');self.addCleanup(helper.doCleanups)
        packet=helper.payload('x,outcome\n1,2\n2,4\n3,6\n4,8\n',group_columns=[])
        source_dir=self.root/'independent-source';source_dir.mkdir()
        source=source_dir/'source.json';source.write_text(canonical(packet))
        project=ResearchProject(self.root/'independent-project')
        state=project.create(source=source,goal='Synthetic missing group',budget_ref='fixture:unknown',
                             max_tool_calls=1,method_id=tabular.TOOL_ID)
        plan={'question':'Synthetic','basis':'No grouping','steps':'Test unknown','expected_feedback':'Wait'}
        project.save_plan(request_id='plan2',expected_state_version=state['state_version'],plan=plan,reason='Synthetic')
        controller=ProjectController(project.root);ctx=controller.selection_context()
        candidate=next(c for c in ctx['candidates'] if c['method_id']==tabular.TOOL_ID)
        project.register_tabular_quality_conditions(request_id='reg2',expected_state_version=ctx['state_version'],
             controller_request_id='q2',candidate_id=candidate['id'],
             conditions=rules(condition('rows','gt',4),condition('group.group_count','gte',1)))
        ctx=controller.selection_context();proposal={'schema_version':'project-selection-proposal-v1',
            'context_sha256':ctx['context_sha256'],'provider':{'kind':'human','label':'synthetic'},
            'choice':{'kind':'execute','candidate_id':candidate['id']},'rationale':'Synthetic', 'evidence_citation_ids':[]}
        controller.advance_selection(request_id='q2',proposal=proposal,expected_state_version=ctx['state_version'])
        result=project.read_tabular_quality_feedback(request_id='reg2')
        self.assertEqual(result['outcome'],'unknown');self.assertEqual(result['unknown_reason'],'quality_values_unknown')
        self.assertEqual([x['outcome'] for x in result['evaluation']['items']],['condition_not_met','unknown'])
        self.assertIsNone(result['action_id']);self.assertEqual(project.status()['budget']['local_tool_calls_used'],1)

    def test_future_id_claimed_by_other_command_is_unknown(self):
        self.register();state=self.project.status()
        self.project.record_feedback(request_id='quality',expected_state_version=state['state_version'],
            author='synthetic',comment='Claim the future ID',next_step='',action_id=None)
        self.assertEqual(self.project.read_tabular_quality_feedback(request_id='reg')['unknown_reason'],
                         'controller_id_claimed_by_other_command')

    def test_changed_parent_and_unfinished_parent_are_unknown(self):
        self.register();self.execute()
        with sqlite3.connect(self.project.db) as con:
            original=con.execute('select record from project where id=1').fetchone()[0]
        for mutate in (lambda p:p['controller_requests'][0].__setitem__('status','unknown'),
                       lambda p:p['controller_requests'][0].__setitem__('decision_sha256','e'*64),
                       lambda p:p['controller_requests'][0]['result']['child'].__setitem__('result_sha256','e'*64)):
            with self.subTest(mutate=mutate):
                self.mutate_project(mutate)
                self.assertEqual(self.project.read_tabular_quality_feedback(request_id='reg')['outcome'],'unknown')
                with sqlite3.connect(self.project.db) as con:con.execute('update project set record=? where id=1',(original,))

    def test_same_id_replay_rejects_changed_core_and_controller_without_write(self):
        record=self.register();original=Path.read_bytes;database=self.project.db.read_bytes()
        import autoresearch.method_registry as registry
        import autoresearch.project_controller as controller_module
        for module in (registry,controller_module):
            path=Path(module.__file__).resolve()
            def drift(p):
                raw=original(p)
                return raw+b'\n# synthetic drift' if p.resolve()==path else raw
            with self.subTest(module=module.__name__),patch.object(Path,'read_bytes',drift):
                with self.assertRaises(ResearchError) as error:
                    self.project.register_tabular_quality_conditions(**record['request'])
                self.assertEqual(error.exception.code,'CODE_CHANGED')
            self.assertEqual(self.project.db.read_bytes(),database)

    def test_rehashed_boolean_conditions_do_not_equal_integer_conditions(self):
        self.register(reg=rules(condition('rows','eq',1)))
        def change(p):
            record=p['tabular_quality_registrations'][0]
            record['request']['conditions']['conditions'][0]['value']=True
            record['request_sha256']=fingerprint(record['request'])
            record['registration_sha256']=fingerprint({k:v for k,v in record.items() if k!='registration_sha256'})
        self.mutate_project(change)
        with self.assertRaises(ResearchError) as error:self.project.read_tabular_quality_feedback(request_id='reg')
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')

    def test_target_without_explicit_state_version_is_unknown(self):
        self.register();ctx=self.controller.selection_context()
        proposal={'schema_version':'project-selection-proposal-v1','context_sha256':ctx['context_sha256'],
                  'provider':{'kind':'human','label':'synthetic'},'choice':{'kind':'execute','candidate_id':self.candidate['id']},
                  'rationale':'Synthetic without explicit state','evidence_citation_ids':[]}
        self.controller.advance_selection(request_id='quality',proposal=proposal,expected_state_version=None)
        self.assertEqual(self.project.read_tabular_quality_feedback(request_id='reg')['outcome'],'unknown')

    def test_duplicate_or_malformed_collection_is_rejected(self):
        self.register()
        with sqlite3.connect(self.project.db) as con:
            original=con.execute('select record from project where id=1').fetchone()[0]
        for bad in (lambda p:p['tabular_quality_registrations'].append(None),
                    lambda p:p['tabular_quality_registrations'].append(copy.deepcopy(p['tabular_quality_registrations'][0]))):
            self.mutate_project(bad)
            with self.assertRaises(ResearchError) as error:self.project.read_tabular_quality_feedback(request_id='reg')
            self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')
            with sqlite3.connect(self.project.db) as con:con.execute('update project set record=? where id=1',(original,))

    def test_corrupted_registration_is_rejected_not_treated_as_evidence(self):
        self.register();self.mutate_project(lambda p:p['tabular_quality_registrations'][0].__setitem__('plan_sha256','e'*64))
        with self.assertRaises(ResearchError) as error:self.project.read_tabular_quality_feedback(request_id='reg')
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')

    def test_new_and_old_future_id_conflicts_both_directions(self):
        # Existing retrieval registration's future ID may not be reused as either new ID.
        self.mutate_project(lambda p:p.update(hypothesis_registrations=[{'request_id':'old','controller_request_id':'future-old'}]))
        for req,target in [('future-old','q'),('new','future-old')]:
            with self.subTest(req=req),self.assertRaises(ResearchError) as error:self.register(req=req,target=target)
            self.assertEqual(error.exception.code,'IDEMPOTENCY_CONFLICT')
        self.mutate_project(lambda p:p.pop('hypothesis_registrations'))
        self.register(req='reg',target='future-new')
        for req,target in [('future-new','q'),('old-new','future-new')]:
            hyp={'candidate_id':self.candidate['id'],'controller_request_id':target,'metric':'recall@20','operator':'gt','threshold':0}
            with self.subTest(req=req),self.assertRaises(ResearchError) as error:
                hypothesis_feedback.register(self.project,request_id=req,expected_state_version=self.project.status()['state_version'],hypothesis=hyp)
            self.assertEqual(error.exception.code,'IDEMPOTENCY_CONFLICT')

if __name__=='__main__':unittest.main()
