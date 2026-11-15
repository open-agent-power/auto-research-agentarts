"""Opt-in validation influence evidence; synthetic fixture only."""
from contextlib import ExitStack
import copy
import json
import os
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_staged_relevance_adapter as fixtures
from autoresearch import (staged_feedback_reader as reader, staged_relevance_adapter as staged,
    retrieval_lexical as lexical, relevance_retrieval_adapter as relevance, retrieval_holdout as holdout,
    saved_materials as materials, research_plan_proposal as plan, recipe_change_proposal as recipe,
    host_model_report, project_report, host_model_selection, method_registry)
from autoresearch.contracts import ResearchError, canonical
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler


class ValidationStabilityTests(unittest.TestCase):
    def fixture(self, multiple=True):
        helper=fixtures.StagedDevelopmentTests();helper.setUp();self.addCleanup(helper.doCleanups)
        if multiple:
            queries=[{'_id':'qd','text':'cat','metadata':{}}, {'_id':'qv','text':'unknown token','metadata':{}},
                     {'_id':'q2','text':'fish','metadata':{}},{'_id':'q3','text':'dog','metadata':{}}]
            (helper.root/'queries.jsonl').write_text(fixtures._rows(queries))
            (helper.root/'qrels.tsv').write_text('query-id\tcorpus-id\tscore\nqd\ta\t2\nqv\tb\t1\nqv\tmissing\t2\nq2\tc\t1\nq3\ta\t1\n')
            helper.spec['query_splits']['validation']=['qv','q2','q3'];helper.write_spec()
        packet=helper.capture();temp=self.enterContext(tempfile.TemporaryDirectory());root=Path(temp)
        (root/'input').mkdir();source=root/'input'/'source.json';source.write_text(canonical(packet))
        project=ResearchProject(root/'project')
        project.create(source=source,goal='Synthetic stability engineering fixture',budget_ref='fixture',max_tool_calls=1,method_id=staged.TOOL_ID)
        project.save_plan(request_id='plan',expected_state_version=project.status()['state_version'],
             plan={'question':'Fixture?', 'basis':'Synthetic only', 'steps':'Saved pair', 'expected_feedback':'Compare results'},reason='Fixture')
        action=project.step(request_id='primary',expected_state_version=project.status()['state_version'])
        return project,action

    def guards(self,project):
        stack=ExitStack();self.addCleanup(stack.close)
        real_path,real_os=Path.open,os.open
        blocked=[project.root/'private_evaluation',project.root/'host-model-selections']
        def check(path):
            if isinstance(path,int):return
            path=Path(os.fsdecode(path)).absolute()
            if any(path==p or path.is_relative_to(p) for p in blocked):raise AssertionError('private read')
        def path_open(path,*a,**kw):check(path);return real_path(path,*a,**kw)
        def os_open(path,*a,**kw):check(path);return real_os(path,*a,**kw)
        stack.enter_context(patch.object(Path,'open',path_open));stack.enter_context(patch.object(os,'open',os_open))
        for obj,name in ((holdout,'_verified_private'),(staged,'execute'),(lexical,'build_index'),(lexical,'retrieve'),
            (lexical,'metrics'),(relevance,'retrieve'),(ResearchProject,'step'),(ResearchProject,'resume'),
            (ResearchProject,'_recover'),(ProjectController,'advance_selection'),(host_model_selection,'run_claude_selection'),
            (Ridge,'fit'),(StandardScaler,'fit')):
            stack.enter_context(patch.object(obj,name,side_effect=AssertionError('no execution')))
        return stack

    def test_saved_reader_and_opt_in_context_are_bound_and_read_once(self):
        project,action=self.fixture();state=project.status()
        selector={'kind':'staged_validation_stability','action_id':action['id'],'result_sha256':action['result_sha256']}
        with self.guards(project),patch.object(reader,'_checked_primary',wraps=reader._checked_primary) as checked:
            context=plan.build_context(project,saved_materials=[selector]);self.assertEqual(checked.call_count,1)
            material=context['supplied_materials'][0]
            self.assertEqual(context['schema_version'],'research-plan-context-v3')
            self.assertEqual(material['binding']['result_sha256'],action['result_sha256'])
            self.assertEqual(set(material['metrics']),{'recall@20','mrr@10'})
            self.assertTrue(all(x['queries']==3 for x in material['metrics'].values()))
            self.assertNotIn('query_id',canonical(material));self.assertNotIn('unknown token',canonical(material))
            self.assertNotIn('final',canonical(material['metrics']))
            self.assertEqual(plan._context(context),context)
            prompt=plan.build_prompt(context)
            self.assertIn('one-query removal only',prompt['system'])
            self.assertIn('does not alter any registered threshold',prompt['system'])
        self.assertEqual(project.status(),state)
        self.assertEqual(state['budget']['local_tool_calls_used'],1)
        self.assertEqual((state['budget']['new_model_requests'],state['budget']['new_fits']),(0,0))

    def test_one_query_has_explicit_unavailable_loo(self):
        project,action=self.fixture(False);state=project.status()
        with self.guards(project):
            result=reader.read_validation_stability(project,state,action_id=action['id'])
            for item in result['metrics'].values():
                self.assertEqual(item['queries'],1);self.assertEqual(item['leave_one_out']['reason'],'fewer_than_two_queries')
                for key in ('minimum','maximum','positive','negative','near_zero','to_near_zero','to_opposite_sign'):
                    self.assertIsNone(item['leave_one_out'][key])
        self.assertEqual(project.status(),state)

    def test_calculated_zero_flip_and_exact_saved_summary(self):
        saved={'mean':1/3,'wins':1,'losses':0,'ties':2}
        item=reader._stability_aggregate([1,0,0],saved)
        self.assertEqual((item['leave_one_out']['minimum'],item['leave_one_out']['maximum']),(0,0.5))
        self.assertEqual((item['leave_one_out']['to_near_zero'],item['leave_one_out']['to_opposite_sign']),(1,0))
        zero=reader._stability_aggregate([1,-1],{'mean':0,'wins':1,'losses':1,'ties':0})
        self.assertIsNone(zero['leave_one_out']['to_near_zero']);self.assertIsNone(zero['leave_one_out']['to_opposite_sign'])
        with self.assertRaises(ResearchError):reader._stability_aggregate([1,0,0],{**saved,'wins':2})

    def test_selector_bounds_tamper_and_offline_extrema_checks(self):
        project,action=self.fixture();state=project.status()
        selector={'kind':'staged_validation_stability','action_id':action['id'],'result_sha256':action['result_sha256']}
        with self.assertRaises(ResearchError):materials.normalize_requests([selector,selector])
        mixed=[selector]+[{'kind':'retrieval_adverse_query','action_id':'other','result_sha256':'a'*64,
                           'split':'validation','query_id':'q'+str(i)} for i in range(4)]
        self.assertEqual(len(materials.normalize_requests(mixed[:4])),4)
        with self.assertRaises(ResearchError):materials.normalize_requests(mixed)
        with self.assertRaises(ResearchError):materials.normalize_requests([{**selector,'split':'final'}])
        context=plan.build_context(project,saved_materials=[selector])
        for kind in ('binding','count_bool','mean','extrema','positive','contract'):
            changed=copy.deepcopy(context);m=changed['supplied_materials'][0];v=m['metrics']['recall@20']
            if kind=='binding':m['binding']['snapshot_ref']='f'*64
            if kind=='count_bool':v['wins']=True
            if kind=='mean':v['saved_mean']=0.123456789
            if kind=='extrema':
                v.update(saved_mean=.15,checked_fsum_mean=.15,wins=3,losses=0,ties=0)
                v['leave_one_out'].update(minimum=.1,maximum=.2,positive=1,negative=0,near_zero=2,original_mean_sign=1,to_near_zero=2,to_opposite_sign=0,reason=None)
            if kind=='positive':v['leave_one_out']['positive']=True
            if kind=='contract':m['contract']['epsilon']=True
            with self.subTest(kind=kind),self.assertRaises(ResearchError):plan._context(changed)
        with self.assertRaises(ResearchError):plan.build_context(project,saved_materials=[{**selector,'result_sha256':'f'*64}])
        self.assertEqual(project.status(),state)

    def test_original_source_artifact_and_sql_fingerprint_are_required(self):
        project,action=self.fixture();state=project.status()
        for path in (project.root/'source.json',project._artifact(action)):
            original=path.read_bytes()
            try:
                if path.name=='source.json':path.write_bytes(original+b' ')
                else:
                    changed=json.loads(original);changed['tool_result']['result']['per_query_metrics'][0]['query_line']+=1
                    path.write_text(canonical(changed))
                with self.subTest(path=path),self.assertRaises(ResearchError):
                    reader.read_validation_stability(project,state,action_id=action['id'])
            finally:path.write_bytes(original)
        with sqlite3.connect(project.db) as con:
            old=con.execute('SELECT fingerprint FROM actions WHERE request_id=?',(action['request_id'],)).fetchone()[0]
            con.execute('UPDATE actions SET fingerprint=? WHERE request_id=?',('f'*64,action['request_id']))
        try:
            with self.assertRaises(ResearchError):reader.read_validation_stability(project,state,action_id=action['id'])
        finally:
            with sqlite3.connect(project.db) as con:con.execute('UPDATE actions SET fingerprint=? WHERE request_id=?',(old,action['request_id']))
        stale=copy.deepcopy(state);stale['snapshot_ref']='f'*64
        with self.assertRaises(ResearchError):reader.read_validation_stability(project,stale,action_id=action['id'])
        self.assertEqual(project.status(),state)

    def test_recipe_rejection_and_host_same_id_report_summary(self):
        project,action=self.fixture();state=project.status()
        selector={'kind':'staged_validation_stability','action_id':action['id'],'result_sha256':action['result_sha256']}
        current={'schema_version':'research-recipe-v1','id':'fixture','version':1,'question':'What next?',
          'scope_match':{'domain':'retrieval','contract':staged.CONTRACT},'need':'next_check',
          'ordered_methods':[{'method_id':staged.TOOL_ID,'evaluation_ref':method_registry.evaluation_ref(staged.TOOL_ID)}],'on_no_match':'wait'}
        with self.assertRaises(ResearchError) as error:recipe.build_context(project,current,'Review',saved_materials=[selector])
        self.assertEqual(error.exception.code,'INVALID_RECIPE_CHANGE_CONTEXT')
        context=plan.build_context(project,saved_materials=[selector])
        with self.assertRaises(ResearchError):recipe._context({'schema_version':'recipe-change-context-v1','research_context':context,'current_recipe':current,'improvement_goal':'Review'})
        journal=host_model_selection.HostModelSelection(project.root)
        spec={'request_id':'plan-stability','provider':'delegated','purpose':'plan','expected_state_version':state['state_version'],
              'decision_limit':1,'cli_budget_usd':.1,'reason':'Synthetic engineering fixture','saved_materials':[selector]}
        with patch.object(host_model_selection,'run_claude_selection',side_effect=AssertionError('no model')):
            record=journal.prepare(**spec)
            with patch.object(plan,'build_context',side_effect=AssertionError('no rematerialization')):
                self.assertEqual(journal.prepare(**spec),record)
                with self.assertRaises(ResearchError):journal.prepare(**{**spec,'saved_materials':[{**selector,'result_sha256':'f'*64}]})
        summary=host_model_report.supplied_material_summaries(record)
        self.assertEqual(summary[0]['kind'],'staged_validation_stability');self.assertNotIn('metrics',summary[0])
        rows=project_report._supplied_material_rows({'host_models':{'records':[record]}})
        self.assertIn('validation',canonical(rows));self.assertNotIn('checked_fsum_mean',canonical(rows))
        self.assertEqual(project.status(),state)
