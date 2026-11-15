"""Operator-declared plan references; synthetic projects, no model or fit."""
import base64
import copy
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pypdf import PdfReader

import test_conditional_staged_continuation as waiting_fixture
import test_local_workbench_http as http_fixture
import test_staged_project_experience as experience_fixture
from autoresearch import hypothesis_feedback, project_report, project_selection, research_plan_proposal
from autoresearch import staged_relevance_adapter as staged
from autoresearch.contracts import ResearchError, canonical
from autoresearch.host_model_selection import HostModelSelection
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
from autoresearch.staged_wait_experience import StagedWaitExperienceMemory


class PlanExperienceReferenceTests(unittest.TestCase):
    fixture = waiting_fixture.ConditionalStagedContinuationTests.fixture
    serve = http_fixture.LocalWorkbenchHTTPTests.serve
    request = http_fixture.LocalWorkbenchHTTPTests.request
    session = http_fixture.LocalWorkbenchHTTPTests.session

    def setup_case(self):
        manager, project, body = self.fixture(execute_primary=False)
        self.assertEqual(manager.continue_staged(body)['phase'], 'waiting')
        memory = StagedWaitExperienceMemory(Path(self.enterContext(tempfile.TemporaryDirectory())) / 'memory')
        result = memory.import_wait(manager.root, body['request_id'])
        entry = memory.recall(result['scope'])['entries'][0]['record']
        bundle = memory.export_case(result['scope'], entry['id'], case_id='waiting-case', version=1,
                         method_card=experience_fixture.StagedExperienceTests.card(), limitations=['Synthetic case only.'])
        state=project.status(); raw=canonical(bundle).encode()
        response=manager.import_experience({'request_id':'case-import','project_id':state['id'],
                 'expected_state_version':state['state_version'],'bundle_base64':base64.b64encode(raw).decode(),
                 'reason':'Save an original engineering waiting case.'})
        ref=response['experience_revision']
        plan={'question':'What follows the wait?', 'basis':'Case is a limited analogy.',
              'steps':'Inspect the target decision.', 'expected_feedback':'Retain the original outcome.'}
        refs={'schema_version':'project-plan-experience-refs-v1','items':[{'case_id':ref['case_id'],
             'case_version':ref['case_version'],'bundle_sha256':ref['bundle_sha256'],
             'applicability_statement':'Both involve the same fixed retrieval method; final remains unmeasured.'}]}
        return manager,project,plan,refs,ref

    @staticmethod
    def body(project, plan, request_id='plan-with-case'):
        return {'request_id':request_id,'project_id':project.status()['id'],
                'expected_state_version':project.status()['state_version'],'plan':plan,
                'reason':'Record an explicit operator comparison; do not transfer a result.'}

    def test_http_original_id_replay_after_retirement_and_plan_context(self):
        manager,project,plan,refs,revision=self.setup_case();plan['experience_case_refs']=refs
        body=self.body(project,plan);before=project.status();host=HostModelSelection(project.root).status()
        server=self.serve(local_workspace=manager,allow_local_actions=True);headers=self.session(server)
        status,response=self.request(server,'/api/local-workbench/plan','POST',body,headers)
        self.assertEqual(status,200,response);self.assertFalse(response['replayed'])
        saved=response['research_plan'];self.assertEqual(saved['experience_case_refs'],refs)
        after=project.status();self.assertEqual(after['budget'],before['budget']);self.assertEqual(after['actions'],before['actions'])
        self.assertEqual(HostModelSelection(project.root).status(),host)
        context=ProjectController(project.root).selection_context()
        self.assertEqual(context['research_plan'],saved)
        self.assertEqual(project_selection.seal_context({k:v for k,v in context.items() if k!='context_sha256'}),context)
        self.assertEqual(research_plan_proposal.build_context(project)['selection_context']['research_plan'],saved)
        rows=project_report._research_plan_rows(after)
        self.assertIn('操作者声明',rows[-1][0]);self.assertIn(refs['items'][0]['bundle_sha256'],rows[-1][1])
        self.assertIn(refs['items'][0]['applicability_statement'],rows[-1][1])
        manager.set_experience_status({'request_id':'retire','project_id':after['id'],
             'expected_state_version':after['state_version'],'case_id':'waiting-case','status':'retired','reason':'Do not use anew.'})
        retired=project.status();self.assertEqual(retired['plan_revisions'][-1],saved)
        self.assertEqual(ProjectController(project.root).selection_context()['research_plan'],saved)
        retired_prompt=research_plan_proposal.build_prompt(research_plan_proposal.build_context(project))
        self.assertIn("operator's historical references and unverified",retired_prompt['system'])
        self.assertIn('do not establish model adoption',retired_prompt['system'])
        status,replay=self.request(server,'/api/local-workbench/plan','POST',body,headers)
        self.assertEqual(status,200,replay);self.assertTrue(replay['replayed']);self.assertEqual(replay['research_plan'],saved)
        child="""import json,sys;from autoresearch.local_workbench import LocalWorkbench\nm=LocalWorkbench(sys.argv[1]);r=m.save_plan(json.loads(sys.stdin.read()));print(json.dumps(r,sort_keys=True))"""
        completed=subprocess.run([sys.executable,'-B','-c',child,str(manager.root)],input=canonical(body),text=True,
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        self.assertEqual(completed.returncode,0,completed.stderr);self.assertTrue(json.loads(completed.stdout)['replayed'])
        self.assertEqual(project.status(),retired)
        invalid=self.body(project,plan,'new-after-retirement')
        with self.assertRaises(ResearchError) as error:manager.save_plan(invalid)
        self.assertEqual(error.exception.code,'INVALID_REQUEST')
        self.assertEqual(project.status(),retired)
        with manager._connect(readonly=True) as con:
            self.assertIsNone(con.execute("SELECT id FROM requests WHERE id='new-after-retirement'").fetchone())
        upgraded=json.loads((project.root/revision['bundle_ref']).read_bytes());upgraded['version']=2
        updated=manager.import_experience({'request_id':'case-upgrade','project_id':retired['id'],
                  'expected_state_version':retired['state_version'],
                  'bundle_base64':base64.b64encode(canonical(upgraded).encode()).decode(),
                  'reason':'An explicitly newer synthetic case.'})
        current=project.status();self.assertEqual(updated['experience_revision']['case_version'],2)
        self.assertEqual(current['plan_revisions'][-1],saved)
        status,replay=self.request(server,'/api/local-workbench/plan','POST',body,headers)
        self.assertEqual(status,200,replay);self.assertTrue(replay['replayed']);self.assertEqual(replay['research_plan'],saved)
        with self.assertRaises(ResearchError):manager.save_plan(self.body(project,plan,'old-case-version'))
        next_plan=copy.deepcopy(plan);next_ref=next_plan['experience_case_refs']['items'][0]
        next_ref['case_version']=2;next_ref['bundle_sha256']=updated['experience_revision']['bundle_sha256']
        revised=manager.save_plan(self.body(project,next_plan,'new-case-version'))
        self.assertEqual(revised['research_plan']['experience_case_refs']['items'][0]['case_version'],2)
        self.assertEqual(project.status()['budget'],before['budget'])

    def test_invalid_references_do_not_accept_manager_intent_or_mutate_project(self):
        manager,project,plan,refs,_=self.setup_case();before=project.status()
        variants=[]
        for change in ('empty','null','duplicate','version_bool','wrong_sha','wrong_version','statement_empty','statement_nul','extra','schema'):
            value=copy.deepcopy(refs)
            if change=='empty':value['items']=[]
            if change=='null':value=None
            if change=='duplicate':value['items'].append(copy.deepcopy(value['items'][0]))
            if change=='version_bool':value['items'][0]['case_version']=True
            if change=='wrong_sha':value['items'][0]['bundle_sha256']='0'*64
            if change=='wrong_version':value['items'][0]['case_version']+=1
            if change=='statement_empty':value['items'][0]['applicability_statement']='   '
            if change=='statement_nul':value['items'][0]['applicability_statement']='bad\x00text'
            if change=='extra':value['items'][0]['unverified']=True
            if change=='schema':value['schema_version']='other'
            variants.append((change,value))
        for name,value in variants:
            with self.subTest(name=name):
                candidate={**plan,'experience_case_refs':value};body=self.body(project,candidate,'invalid-'+name)
                with self.assertRaises(ResearchError):manager.save_plan(body)
                self.assertEqual(project.status(),before)
                with manager._connect(readonly=True) as con:
                    self.assertIsNone(con.execute('SELECT id FROM requests WHERE id=?',(body['request_id'],)).fetchone())

    def test_same_id_full_body_conflict_and_original_case_bytes_required(self):
        manager,project,plan,refs,revision=self.setup_case();plan['experience_case_refs']=refs
        body=self.body(project,plan);saved=manager.save_plan(body);after=project.status()
        modified=copy.deepcopy(body);modified['plan']['experience_case_refs']['items'][0]['applicability_statement']='Changed statement.'
        with self.assertRaises(ResearchError) as error:manager.save_plan(modified)
        self.assertEqual(error.exception.code,'IDEMPOTENCY_CONFLICT');self.assertEqual(project.status(),after)
        path=project.root/revision['bundle_ref'];raw=path.read_bytes();path.write_bytes(raw+b' ')
        with self.assertRaises(ResearchError) as error:project.status()
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')
        with self.assertRaises(ResearchError):manager.save_plan(body)
        path.write_bytes(raw)
        self.assertEqual(project.status(),after);self.assertTrue(manager.save_plan(body)['replayed'])
        self.assertEqual(saved['research_plan']['experience_case_refs'],refs)

    def test_completed_reference_plan_conflict_precedes_other_pending_without_bypass(self):
        manager,project,plan,refs,_=self.setup_case();plan['experience_case_refs']=refs
        body=self.body(project,plan);manager.save_plan(body);before=project.status()
        stale={'request_id':'stale-legacy', 'project_id':before['id'],
               'expected_state_version':body['expected_state_version'],
               'plan':{k:plan[k] for k in ('question','basis','steps','expected_feedback')},
               'reason':'Keep the original stale intent.'}
        with self.assertRaises(ResearchError) as error:manager.save_plan(stale)
        self.assertEqual(error.exception.code,'STALE_STATE')
        manager_before,project_before=manager.db.read_bytes(),project.db.read_bytes()
        changed=copy.deepcopy(body)
        changed['plan']['experience_case_refs']['items'][0]['applicability_statement']='Different statement.'
        for candidate,code in ((changed,'IDEMPOTENCY_CONFLICT'),(body,'OPERATION_INCOMPLETE'),
                               (self.body(project,plan,'new-versioned'),'OPERATION_INCOMPLETE')):
            with self.subTest(code=code),self.assertRaises(ResearchError) as error:manager.save_plan(candidate)
            self.assertEqual(error.exception.code,code)
            self.assertEqual((manager.db.read_bytes(),project.db.read_bytes()),(manager_before,project_before))
            self.assertEqual(project.status(),before)

    def test_interruption_after_manager_accept_and_state_drift_never_rebinds(self):
        manager,project,plan,refs,_=self.setup_case();plan['experience_case_refs']=refs
        body=self.body(project,plan);original=ResearchProject.save_plan
        def interrupted(target, **kwargs):
            if kwargs.get('_validate_only'):
                return original(target, **kwargs)
            raise KeyboardInterrupt('Synthetic crash after original manager intent')
        with patch.object(ResearchProject,'save_plan',interrupted), self.assertRaises(KeyboardInterrupt):
            manager.save_plan(body)
        with manager._connect(readonly=True) as con:
            row=con.execute('SELECT digest,record FROM requests WHERE id=?',(body['request_id'],)).fetchone()
            self.assertIsNotNone(row);pending=(row['digest'],row['record'])
            self.assertEqual(json.loads(row['record'])['status'],'preparing')
        before=project.status()
        project.set_experience_status(request_id='direct-retire',expected_state_version=before['state_version'],
                                      case_id='waiting-case',status='retired',reason='Synthetic intervening decision.')
        after=project.status()
        with self.assertRaises(ResearchError) as error:manager.save_plan(body)
        self.assertEqual(error.exception.code,'STALE_STATE');self.assertEqual(project.status(),after)
        with manager._connect(readonly=True) as con:
            row=con.execute('SELECT digest,record FROM requests WHERE id=?',(body['request_id'],)).fetchone()
            self.assertEqual((row['digest'],row['record']),pending)
        self.assertFalse(any(x['request_id']==body['request_id'] for x in after.get('plan_revisions',[])))
        self.assertEqual(after['budget'],before['budget']);self.assertEqual(after['actions'],before['actions'])

    def test_persisted_plan_cannot_claim_current_state_as_its_based_on_version(self):
        manager,project,plan,refs,_=self.setup_case();plan['experience_case_refs']=refs
        body=self.body(project,plan);manager.save_plan(body)
        with project._writer(), project._connect() as con:
            raw=project._project(con)
            self.assertLess(raw['plan_revisions'][-1]['based_on_state_version'],raw['state_version'])
            raw['plan_revisions'][-1]['based_on_state_version']=raw['state_version']
            project._save(con,raw)
        damaged=project.db.read_bytes()
        with self.assertRaises(ResearchError) as error:project.status()
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')
        with self.assertRaises(ResearchError) as error:project_report.collect_report(project.root)
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')
        with self.assertRaises(ResearchError):manager.save_plan(body)
        self.assertEqual(project.db.read_bytes(),damaged)

    def test_plan_revision_before_original_primary_preserves_registration_binding_and_unknown(self):
        manager,project,plan,refs,_=self.setup_case();registration=project.status()['hypothesis_registrations'][0]
        plan['experience_case_refs']=refs;manager.save_plan(self.body(project,plan))
        context=ProjectController(project.root).selection_context()
        proposal={'schema_version':'project-selection-proposal-v1','context_sha256':context['context_sha256'],
                  'provider':{'kind':'human','label':'Synthetic fixture'},
                  'choice':{'kind':'execute','candidate_id':registration['candidate']['id']},
                  'rationale':'Run the original synthetic primary after revising the plan.','evidence_citation_ids':[]}
        ProjectController(project.root).advance_selection(request_id='primary',proposal=proposal,expected_state_version=context['state_version'])
        state=project.status();item=hypothesis_feedback.feedback_context(project,state)['items'][0]
        self.assertEqual(item['outcome'],'unknown');self.assertEqual(item['unknown_reason'],'controller_binding_changed')
        self.assertIsNone(item['value']);self.assertIsNone(item['action_id'])
        self.assertEqual(state['hypothesis_registrations'][0],registration)
        self.assertEqual((state['budget']['local_tool_calls_used'],state['budget']['new_fits'],state['budget']['new_model_requests']),(1,0,0))

    def test_existing_known_feedback_remains_known_but_changed_plan_blocks_policy_and_freeze(self):
        source_manager,source,plan,refs,revision=self.setup_case()
        raw=(source.root/revision['bundle_ref']).read_bytes()
        manager,project,_=self.fixture('positive',execute_primary=True)
        before=project.status();prior=hypothesis_feedback.feedback_context(project,before)['items'][0]
        self.assertEqual(prior['outcome'],'condition_met')
        manager.import_experience({'request_id':'new-case','project_id':before['id'],'expected_state_version':before['state_version'],
                                   'bundle_base64':base64.b64encode(raw).decode(),'reason':'Synthetic analogy only.'})
        plan['experience_case_refs']=refs;manager.save_plan(self.body(project,plan))
        state=project.status();after=hypothesis_feedback.feedback_context(project,state)['items'][0]
        self.assertEqual(after,prior)
        decision=ProjectController(project.root).advance_feedback(request_id='after-plan-feedback',
                    registration_request_id='prediction',expected_state_version=state['state_version'])
        self.assertEqual(decision['status'],'waiting')
        current=project.status();self.assertEqual(current['budget'],state['budget']);self.assertEqual(current['actions'],state['actions'])
        with self.assertRaises(ResearchError) as error:
            project.freeze_retrieval_strategy(request_id='after-plan-freeze',expected_state_version=current['state_version'],
                                              primary_action_id=current['actions'][0]['id'])
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED');self.assertEqual(project.status(),current)

    def test_legacy_plan_selection_keeps_original_wire(self):
        _,project,_,_,_=self.setup_case()
        context=ProjectController(project.root).selection_context()
        payload={k:v for k,v in context.items() if k!='context_sha256'}
        self.assertEqual(project_selection.seal_context(payload),context)
        plan=research_plan_proposal.build_context(project)
        self.assertEqual(set(plan['selection_context']['research_plan']),
                         {'question','basis','steps','expected_feedback','version','request_id','based_on_state_version','reason'})
        self.assertNotIn('project-plan-experience-refs-v1',canonical(research_plan_proposal.build_prompt(plan)))

    def test_all_four_maximum_statements_are_complete_in_markdown_and_pdf(self):
        manager,project,plan,refs,revision=self.setup_case()
        old=project.status()['plan_revisions'][-1]
        old_rows=project_report._research_plan_rows(project.status())
        self.assertEqual(old_rows, [('当前版本','第'+str(old['version'])+'版'),('本轮问题',old['question']),
             ('依据与材料',old['basis'] or '尚未填写'),('推进步骤',old['steps']),
             ('预期反馈与调整',old['expected_feedback']),('本次修订理由',old['reason']),
             ('修订记录','\n'.join('第'+str(x['version'])+'版 · '+x['reason'] for x in project.status()['plan_revisions']))])
        original=json.loads((project.root/revision['bundle_ref']).read_bytes())
        entries=[refs['items'][0]]
        for index in range(2,5):
            bundle=copy.deepcopy(original);bundle['id']='waiting-case-'+str(index)
            state=project.status()
            saved=manager.import_experience({'request_id':'import-'+str(index),'project_id':state['id'],
                   'expected_state_version':state['state_version'],'bundle_base64':base64.b64encode(canonical(bundle).encode()).decode(),
                   'reason':'Distinct synthetic case for bounded report rendering.'})['experience_revision']
            entries.append({'case_id':saved['case_id'],'case_version':saved['case_version'],
                            'bundle_sha256':saved['bundle_sha256'],'applicability_statement':'placeholder'})
        for index, item in enumerate(entries,1):
            prefix='start'+str(index)+'-';suffix='-end'+str(index)
            item['applicability_statement']=prefix+('x'*(1000-len(prefix)-len(suffix)))+suffix
            self.assertEqual(len(item['applicability_statement']),1000)
        plan['experience_case_refs']={'schema_version':'project-plan-experience-refs-v1','items':entries}
        manager.save_plan(self.body(project,plan))
        rows=project_report._research_plan_rows(project.status())
        plan_rows=[row for row in rows if row[0].startswith('操作者声明的历史案例引用')]
        self.assertEqual(len(plan_rows),4)
        report=project_report.collect_report(project.root)
        markdown=project_report._markdown(report)
        pdf=''.join(page.extract_text() or '' for page in PdfReader(BytesIO(project_report._pdf(report))).pages)
        compact_pdf=''.join(pdf.split())
        for item,row in zip(entries,plan_rows):
            self.assertIn(item['case_id'],row[1]);self.assertIn(item['bundle_sha256'],row[1])
            self.assertIn(item['applicability_statement'],row[1])
            self.assertIn(row[1],markdown)
            self.assertIn(item['case_id'],compact_pdf);self.assertIn(item['bundle_sha256'],compact_pdf)
            self.assertIn(item['applicability_statement'],compact_pdf)


if __name__=='__main__':unittest.main()
