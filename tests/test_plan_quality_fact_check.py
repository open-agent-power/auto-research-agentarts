"""Quality span checks against frozen synthetic Host materials, with no model calls."""
import copy
import json
import unittest
from unittest.mock import patch

import test_local_workbench_http as http
import test_tabular_quality_feedback as conditions
import test_tabular_quality_workbench as fixture
from autoresearch import plan_fact_check
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject


class PlanQualityFactTests(unittest.TestCase):
    serve = http.LocalWorkbenchHTTPTests.serve
    request = http.LocalWorkbenchHTTPTests.request
    session = http.LocalWorkbenchHTTPTests.session

    def stage(self, *, execute=True, supplied=True, no_groups=False, not_met=False):
        helper = fixture.QualityWorkbenchTests('runTest')
        if no_groups:
            original=conditions.fixtures.NumericAssociationTests.payload
            def without_groups(instance, csv, **kwargs):
                return original(instance,'x,outcome\n1,2\n2,4\n3,6\n4,8\n',group_columns=[])
            with patch.object(conditions.fixtures.NumericAssociationTests,'payload',new=without_groups):
                f,manager,reg_body=helper.stage()
        else:
            f,manager,reg_body=helper.stage()
        self.addCleanup(helper.doCleanups)
        reg_body['conditions'] = (conditions.rules(conditions.condition('rows','gt',4),
            conditions.condition('group.group_count','gte',1)) if no_groups else
            conditions.rules(conditions.condition('rows','gt' if not_met else 'eq',4),
            conditions.condition('exact_duplicate_rows','eq',0), {'field':'flags','operator':'empty'}))
        reg = manager.register_tabular_quality_conditions(reg_body)['registration']
        if execute: f.execute()
        selector = {'kind':'tabular_quality_feedback','registration_request_id':'reg',
                    'registration_sha256':reg['registration_sha256']}
        host = HostModelSelection(f.project.root)
        host.prepare(request_id='fact-quality',provider='delegated',purpose='plan',
            expected_state_version=f.project.status()['state_version'],decision_limit=1,cli_budget_usd=.1,
            reason='Synthetic fixture',saved_materials=[selector] if supplied else None)
        actions=f.project.status()['actions']
        args={'plan':{'question':'🧪 Quality claim remains explicit.', 'basis':'Synthetic observation',
                      'steps':'Inspect the saved result.', 'expected_feedback':'Keep uncertainty.'},
              'reason':'An operator supplied this test response.', 'expected_improvement':'Check the assertion.',
              'feedback_action_ids':[actions[0]['id']] if actions else []}
        path=f.root/'delegated-fact.json';path.write_text(canonical(args),encoding='utf-8')
        host.import_response(request_id='fact-quality',response_file=path)
        self.assertEqual(host.consume(request_id='fact-quality')['status'],'proposed')
        claim={'field':'plan.question','start':2,'end':len(args['plan']['question']),
               'quote':args['plan']['question'][2:], 'quality':{'registration_request_id':'reg',
               'registration_sha256':reg['registration_sha256']},
               'assertion':{'kind':'overall_outcome','value':'condition_met'}}
        body={'project_id':f.project.status()['id'],'host_request_id':'fact-quality','claim':claim}
        return f,manager,host,body

    def test_original_host_material_overall_values_zero_and_flags(self):
        f,manager,host,body=self.stage(); before=f.project.status();db=f.project.db.read_bytes()
        with patch.object(ResearchProject,'step',side_effect=AssertionError('step')), \
             patch.object(ProjectController,'_dispatch',side_effect=AssertionError('dispatch')), \
             patch('autoresearch.host_model_selection.run_claude_selection',side_effect=AssertionError('model')):
            result=manager.check_plan_fact(body)
            self.assertEqual((result['status'],result['actual']),('supported','condition_met'))
            record=host.status(request_id='fact-quality')
            self.assertEqual(result['context_sha256'],fingerprint(record['context']))
            self.assertEqual(result['response_sha256'],record['response_sha256'])
            self.assertEqual(result['material_sha256'],fingerprint(record['context']['supplied_materials'][0]))
            self.assertEqual(result['coverage'],'selected_span_only')
            self.assertEqual(result['semantic_mapping'],'submitter_declared')
            self.assertFalse(result['scientific_validation'])
            cases=[({'kind':'condition_value','index':1,'field':'actual','value':0},'supported',0),
                   ({'kind':'condition_value','index':1,'field':'expected','value':1},'contradicted',0),
                   ({'kind':'condition_value','index':2,'field':'actual','value':'empty'},'supported','empty'),
                   ({'kind':'condition_outcome','index':0,'value':'condition_not_met'},'contradicted','condition_met')]
            for assertion,status,actual in cases:
                with self.subTest(assertion=assertion):
                    body['claim']['assertion']=assertion;out=manager.check_plan_fact(body)
                    self.assertEqual((out['status'],out['actual']),(status,actual))
        self.assertEqual(f.project.status(),before);self.assertEqual(f.project.db.read_bytes(),db)
        self.assertEqual(before['budget']['local_tool_calls_used'],1)

    def test_unknown_and_missing_material_are_undetermined_without_fabricated_values(self):
        f,manager,_,body=self.stage(execute=False)
        body['claim']['assertion']={'kind':'overall_outcome','value':'unknown'}
        self.assertEqual(manager.check_plan_fact(body)['status'],'supported')
        body['claim']['assertion']['value']='condition_not_met'
        result=manager.check_plan_fact(body);self.assertEqual((result['status'],result['actual']),('undetermined','unknown'))
        body['claim']['assertion']['value']='condition_met'
        self.assertEqual(manager.check_plan_fact(body)['status'],'undetermined')
        body['claim']['assertion']={'kind':'condition_value','index':1,'field':'actual','value':0}
        result=manager.check_plan_fact(body);self.assertEqual((result['status'],result['actual']),('undetermined',None))
        body['claim']['quality']['registration_sha256']='0'*64
        result=manager.check_plan_fact(body);self.assertEqual((result['status'],result['material_sha256']),('undetermined',None))
        self.assertEqual(f.project.status()['budget']['local_tool_calls_used'],0)
        _,manager,_,body=self.stage(supplied=False)
        result=manager.check_plan_fact(body)
        self.assertEqual((result['status'],result['reason_code']),('undetermined','quality_material_not_supplied'))

    def test_unknown_item_preserves_known_other_condition_and_unknown_precedence(self):
        _,manager,_,body=self.stage(no_groups=True)
        body['claim']['assertion']={'kind':'overall_outcome','value':'condition_not_met'}
        result=manager.check_plan_fact(body)
        self.assertEqual((result['status'],result['actual'],result['feedback_unknown_reason']),
                         ('undetermined','unknown','quality_values_unknown'))
        self.assertIn('does not establish that execution did not occur',result['notice'])
        for claim,status in (({'kind':'overall_outcome','value':'unknown'},'supported'),
                             ({'kind':'condition_outcome','index':1,'value':'unknown'},'supported'),
                             ({'kind':'condition_outcome','index':1,'value':'condition_met'},'undetermined'),
                             ({'kind':'condition_outcome','index':1,'value':'condition_not_met'},'undetermined'),
                             ({'kind':'condition_value','index':1,'field':'actual','value':0},'undetermined'),
                             ({'kind':'condition_outcome','index':0,'value':'condition_not_met'},'supported'),
                             ({'kind':'condition_value','index':0,'field':'actual','value':4},'supported')):
            with self.subTest(claim=claim):
                body['claim']['assertion']=claim;result=manager.check_plan_fact(body)
                self.assertEqual(result['status'],status)
                self.assertEqual(result['overall_outcome'],'unknown')

    def test_known_unmet_is_not_unknown(self):
        _,manager,_,body=self.stage(not_met=True)
        body['claim']['assertion']['value']='condition_not_met'
        result=manager.check_plan_fact(body)
        self.assertEqual((result['status'],result['overall_outcome']),('supported','condition_not_met'))

    def test_invalid_types_indices_and_spans_are_rejected(self):
        _,manager,_,body=self.stage()
        bad=[{'kind':'condition_value','index':1,'field':'actual','value':False},
             {'kind':'condition_value','index':True,'field':'actual','value':0},
             {'kind':'condition_value','index':2,'field':'actual','value':0},
             {'kind':'condition_value','index':1,'field':'actual','value':'empty'},
             {'kind':'condition_outcome','index':31,'value':'condition_met'}]
        for assertion in bad:
            with self.subTest(assertion=assertion):
                wrong=copy.deepcopy(body);wrong['claim']['assertion']=assertion
                with self.assertRaises(ResearchError):manager.check_plan_fact(wrong)
        wrong=copy.deepcopy(body);wrong['claim']['start']=3
        with self.assertRaises(ResearchError):manager.check_plan_fact(wrong)

    def test_missing_or_tampered_host_originals_cannot_be_checked(self):
        f,manager,host,body=self.stage();record=host.status(request_id='fact-quality')
        for relative in (record['directory']+'/context.json',record['directory']+'/prompt.json',
                         record['directory']+'/proposal.json',record['response_file']):
            with self.subTest(relative=relative):
                path=host.directory/relative; raw=path.read_bytes();path.unlink()
                try:
                    with self.assertRaises(ResearchError):manager.check_plan_fact(body)
                finally:path.write_bytes(raw)
        state=host._load(); old=copy.deepcopy(state)
        del state['requests']['fact-quality']['response_file'];host._save(state)
        try:
            with self.assertRaises(ResearchError):manager.check_plan_fact(body)
        finally:host._save(old)
        path=host.directory/record['response_file'];raw=path.read_bytes()
        try:
            path.write_bytes(raw+b' ')
            with self.assertRaises(ResearchError):manager.check_plan_fact(body)
        finally:path.write_bytes(raw)
        self.assertEqual(manager.check_plan_fact(body)['status'],'supported')

    def test_later_plan_uses_only_the_original_frozen_material(self):
        f,manager,_,body=self.stage(); first=manager.check_plan_fact(body)
        state=f.project.status()
        f.project.save_plan(request_id='later-plan',expected_state_version=state['state_version'],
            plan={'question':'Later','basis':'Synthetic','steps':'Wait','expected_feedback':'Keep unknown'},reason='Test')
        with patch.object(ResearchProject,'read_tabular_quality_feedback',side_effect=AssertionError('live feedback')):
            result=manager.check_plan_fact(body)
        self.assertEqual(result,first)

    def test_resealed_prompt_must_still_derive_from_original_context(self):
        _,manager,host,body=self.stage()
        saved=host._load(); modified=copy.deepcopy(saved)
        record=modified['requests']['fact-quality']
        prompt_path=host.directory/record['directory']/'prompt.json'
        original_prompt=prompt_path.read_bytes()
        record['prompt']['prompt']='A different synthetic prompt with no supplied quality material.'
        prompt_path.write_bytes(canonical(record['prompt']).encode('utf-8'))
        host._save(modified)
        try:
            with self.assertRaises(ResearchError) as error:manager.check_plan_fact(body)
            self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')
        finally:
            prompt_path.write_bytes(original_prompt);host._save(saved)
        self.assertEqual(manager.check_plan_fact(body)['status'],'supported')

    def test_http_origin_readonly_and_no_ledger_write(self):
        f,manager,_,body=self.stage();before=(f.project.db.read_bytes(),manager.db.read_bytes())
        server=self.serve(local_workspace=manager,allow_local_actions=True);headers=self.session(server)
        status,result=self.request(server,'/api/local-workbench/plan-fact-check','POST',body,headers)
        self.assertEqual((status,result['status']),(200,'supported'))
        status,_=self.request(server,'/api/local-workbench/plan-fact-check','POST',body,{**headers,'Origin':'http://evil.invalid'})
        self.assertNotEqual(status,200)
        readonly=self.serve(local_workspace=LocalWorkbench.open_readonly(manager.root),allow_local_actions=False)
        status,_=self.request(readonly,'/api/local-workbench/plan-fact-check','POST',body,headers)
        self.assertNotEqual(status,200)
        self.assertEqual((f.project.db.read_bytes(),manager.db.read_bytes()),before)


if __name__=='__main__':unittest.main()
