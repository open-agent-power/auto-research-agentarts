"""Scripted transport tests; actual model/credit evidence is separate in runs/."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from autoresearch.c01_cloud_loop import C01CloudLoop, MODEL, REMOTE_MODEL, ALIAS_SHA, CONFIG_SHA, SYSTEM_CLOUD
from autoresearch.c01_local_loop import C01LocalLoop
from autoresearch.c01_research import control_review_state
from autoresearch.contracts import ResearchError,canonical,fingerprint
import test_c01_research as fixture
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import c01_model_fixture
import run_cloud_research as cli

IDENTITY={'model':MODEL,'remote_model':REMOTE_MODEL,'remote_host':'https://ollama.com:443',
          'alias_sha256':ALIAS_SHA,'config_sha256':CONFIG_SHA,'account_identity_sha256':'d'*64,
          'account_period':{'from':'2026-10-18T00:00:00Z','until':'2026-11-18T00:00:00Z'}}


def scripted_read(context):
    card=context['source_catalogue']['documents'][0]
    return {'action':'read_source','observation_sha256':context['observation_sha256'],
            'reason':'SYNTHETIC reader contract fixture, not model research.',
            'source_citation_ids':[],'evidence_action_ids':[],
            'parameters':{'document_id':card['document_id'],'source_sha256':card['source_sha256'],
                          'start_chunk':0,'count':1}}


def scripted_control_review(context):
    control=context['control_review']
    return {'action':'review_evidence','observation_sha256':context['observation_sha256'],
            'reason':'SYNTHETIC review/recovery contract, not a scientific or model result.',
            'source_citation_ids':context['known_source_citation_ids'][:1],
            'evidence_action_ids':[control['proposal_action_id']]+([control['latest_experiment_id']] if control['latest_experiment_id'] else []),
            'parameters':{'field':'control_rationale','question':'Does the original fixture rationale follow?',
                'finding':'The fixture alone does not establish scientific validity.','status':'unresolved',
                'next_check':'The actor must choose a justified next step from the preserved feedback.'}}


class FakeCloud:
    def __init__(self,policy=None,before=None,identity=None):
        self.http=self;self.identity=copy.deepcopy(IDENTITY if identity is None else identity)
        self.requests=[];self.budgets=[];self.policy=policy or c01_model_fixture.decision;self.before=before
        self.credit_hold=None
    def assert_owner(self):pass
    def acquire(self):return copy.deepcopy(self.identity)
    def configure_budget(self,identity,remaining):
        assert identity==self.identity
        self.budgets.append(remaining)
    def prepare(self,body):pass
    def request(self,route,body,*,timeout):
        assert route=='/api/chat' and timeout==90 and body['model']==MODEL and 'format' not in body
        self.requests.append(copy.deepcopy(body))
        if self.before:self.before(body)
        context=json.loads(body['messages'][-1]['content'])['research_context']
        chosen=self.policy(context)
        message={'content':chosen} if isinstance(chosen,str) else {'content':'', 'tool_calls':[{'function':{
                  'name':chosen['action'],'arguments':{**{key:value for key,value in chosen.items() if key not in {'action','parameters'}},
                                                       **chosen['parameters']}}}]}
        return {'model':REMOTE_MODEL,'done':True,'prompt_eval_count':1234,'eval_count':123,
                'message':message,'simulation_notice':'scripted; not a cloud inference'}


class CloudLoopTests(unittest.TestCase):
    def setUp(self):
        self.base=fixture.C01ResearchTests('test_terminal_decision_is_durable_and_stops_new_dispatch')
        self.base.setUp();self.addCleanup(self.base.doCleanups)
        self.study=self.base.study;self.loop=C01CloudLoop(self.study.root)

    def configure(self,maximum=8):return self.loop.configure(copy.deepcopy(IDENTITY),max_requests=maximum)

    def test_method_semantics_reach_native_actor_and_critic_without_selecting_a_recipe_or_fitting(self):
        self.base.search()
        self.loop=C01CloudLoop(self.study.root,tool_profile='reviewed_modeler')
        with patch('autoresearch.c01_research.c01._round',side_effect=AssertionError('metadata must not execute a fit')):
            self.configure();spec=self.saved_spec();observation=self.study.observe();original=copy.deepcopy(observation)
            actor=self.loop._request(observation,8,[],spec)
            self.assertEqual(observation,original)
            functions={t['function']['name']:t['function'] for t in actor['tools']}
            alpha=functions['fit']['parameters']['properties']['alpha']
            self.assertEqual({k:v for k,v in alpha.items() if k!='description'},
                             {'type':'number','minimum':0.001,'maximum':10000})
            self.assertIn('larger alpha means stronger',alpha['description'])
            self.assertIn('does not guarantee lower held-out error',functions['fit']['description'])
            self.assertIn('water_contact_angle_deg and cell_seeding_efficiency_24h_pct',functions['correlation']['description'])
            self.assertNotIn('alp_norm_d21',functions['correlation']['description'])
            self.base.propose()
            critic=self.loop._request(self.study.observe(),7,[],spec)
        actor_context=json.loads(actor['messages'][1]['content'])['research_context']
        critic_context=json.loads(critic['messages'][1]['content'])['research_context']
        self.assertEqual(actor_context['execution_role'],'actor')
        self.assertEqual(critic_context['execution_role'],'critic')
        self.assertEqual(self.loop._offered_actions(critic),{'review_evidence'})
        for context in (actor_context,critic_context):
            method=context['project_evaluation_protocol']
            self.assertIn('alpha * ||w||_2^2',method['objective'])
            self.assertIn('No refitting',method['diagnostic_tools']['residuals'])
            self.assertNotIn('alpha',method)  # Facts about the method do not choose a numerical recipe.
        self.assertEqual(self.loop.status()['budget']['requests_reserved'],0)

    def inspection_study(self):
        self.study=type(self.study)(self.base.root/'inspection-study')
        with patch('autoresearch.c01_research.c01.load_archive',return_value=self.base.inspection_inputs()):
            self.study.create('synthetic-inspection-only.zip',self.base.index,'Synthetic inspection/recovery only',max_fits=2)
        self.loop=C01CloudLoop(self.study.root)

    def saved_spec(self):
        with self.loop._connect() as con:
            return json.loads(con.execute('SELECT spec_json FROM project').fetchone()[0])

    def modeler(self,maximum=4):
        self.loop=C01CloudLoop(self.study.root,tool_profile='as_reported_modeler')
        return self.configure(maximum)

    def reviewed(self,maximum=8):
        self.loop=C01CloudLoop(self.study.root,tool_profile='reviewed_modeler')
        return self.configure(maximum)

    def propose(self):
        return self.study.apply(self.base.request('propose_control',{'decision':'pause'},
            reason='SYNTHETIC original control rationale, not a scientific conclusion.'))

    def review(self):
        state=self.study.observe();control=control_review_state(state)
        evidence=[control['proposal_action_id']]+([control['latest_experiment_id']] if control['latest_experiment_id'] else [])
        return self.study.apply(self.base.request('review_evidence',
            {'field':'control_rationale','question':'Does the original synthetic rationale follow from the available evidence?',
             'finding':'Synthetic test judgement remains unreviewed; the fixture does not establish causal explanation.',
             'status':'unresolved','next_check':'Choose a justified current action from the original evidence and feedback.'},
            evidence_action_ids=evidence))

    def test_invalid_profile_is_rejected_before_workspace_or_superclass_io(self):
        destination=self.base.root/'must-not-be-created'
        for profile in (None,True,'','GENERAL','unknown','critic','actor','budget_control','../general',[],{}):
            with self.subTest(profile=profile),patch.object(C01LocalLoop,'__init__',side_effect=AssertionError('no superclass IO')) as init:
                with self.assertRaises(ResearchError) as error:C01CloudLoop(destination,tool_profile=profile)
                self.assertEqual(error.exception.code,'INVALID_REQUEST');init.assert_not_called()
        self.assertFalse(destination.exists())

    def test_general_default_and_modeler_permissions_intersect_actual_source_and_terminal_permissions(self):
        general=self.loop._specification(IDENTITY,self.study.observe(),4)
        general_body=self.loop._request(self.study.observe(),4,[],general)
        self.assertEqual(general['tool_profile'],'general')
        self.assertEqual(general_body['messages'][0]['content'],SYSTEM_CLOUD)
        self.assertEqual(self.loop._offered_actions(general_body),{'pause','stop','inspect_dataset','search','read_source'})
        status=self.modeler();spec=self.saved_spec();observation=self.study.observe()
        before=(canonical(spec),canonical(observation))
        body=self.loop._request(observation,4,[],spec)
        self.assertEqual(status['tool_profile'],'as_reported_modeler')
        self.assertEqual(status['permitted_tool_names'],['correlation','fit','inspect_dataset','pause','residuals','stop'])
        self.assertEqual(spec['schema'],'c01-owned-cloud-native-tools-v11-control-review')
        self.assertEqual(self.loop._offered_actions(body),{'pause','stop','inspect_dataset'})
        self.assertIn('operator-provided',body['messages'][0]['content'])
        self.assertIn('no fit or positive result is compulsory',body['messages'][0]['content'])
        self.assertEqual(before,(canonical(spec),canonical(observation)))
        terminal=self.loop._request(observation,1,[],spec)
        self.assertEqual(self.loop._offered_actions(terminal),{'pause','stop'})
        observation['budget']['actions_used']=observation['budget']['max_actions']-1
        self.assertEqual(self.loop._offered_actions(self.loop._request(observation,4,[],spec)),{'pause','stop'})

    def test_stored_modeler_profile_is_authoritative_and_reconfigure_drift_is_refused(self):
        configured=self.modeler();before=self.loop.status()
        general_instance=C01CloudLoop(self.study.root)
        self.assertEqual(general_instance.status(),before)
        body=general_instance._request(before['study'],4,[],self.saved_spec())
        self.assertNotIn('search',general_instance._offered_actions(body))
        with self.assertRaises(ResearchError) as error:general_instance.configure(copy.deepcopy(IDENTITY),max_requests=4)
        self.assertEqual(error.exception.code,'CONFIG_CHANGED')
        self.assertEqual(self.loop.status(),configured)

    def test_unknown_or_broadened_profile_spec_fails_before_transport_or_reservation(self):
        self.modeler();spec=self.saved_spec();observation=self.study.observe()
        changes=[{'tool_profile':'unknown'}, {'permitted_tool_names':spec['permitted_tool_names']+['search']},
                 {'tool_profile':'general'}, {'permitted_tool_names':['pause','stop']},
                 {'schema':'old-schema'}]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ResearchError) as error:
                self.loop._request(observation,4,[],{**spec,**change})
            self.assertEqual(error.exception.code,'CONFIG_CHANGED')
        altered={**spec,'tool_profile':'unknown'}
        with self.loop._connect(True) as con:
            con.execute('UPDATE project SET spec_json=?,spec_sha256=?',(canonical(altered),fingerprint(altered)))
        server=FakeCloud()
        with patch.object(server,'acquire',side_effect=AssertionError('no acquire')), \
             patch.object(server,'prepare',side_effect=AssertionError('no preflight')):
            with self.assertRaises(ResearchError) as error:self.loop.run(server,max_new_requests=1)
        self.assertEqual(error.exception.code,'CONFIG_CHANGED');self.assertEqual(server.requests,[])
        with self.loop._connect() as con:self.assertEqual(con.execute('SELECT count(*) FROM calls').fetchone()[0],0)

    def test_saved_modeler_tool_table_controls_offline_response_recovery(self):
        self.modeler();server=FakeCloud()  # Without sources this fixture attempts search, which is not offered.
        with patch.object(self.loop,'_consume',side_effect=RuntimeError('after received')):
            with self.assertRaises(RuntimeError):self.loop.run(server,max_new_requests=1)
        with self.loop._connect() as con:
            saved=json.loads(con.execute('SELECT request_json FROM calls').fetchone()[0])
        self.assertEqual(self.loop._offered_actions(saved),{'pause','stop','inspect_dataset'})
        result=C01CloudLoop(self.study.root).run(max_new_requests=0)
        self.assertEqual(result['tool_profile'],'as_reported_modeler')
        self.assertEqual(result['calls'][0]['error_code'],'ACTION_NOT_AVAILABLE')
        self.assertEqual(result['study']['actions'],[]);self.assertEqual(len(server.requests),1)

    def test_modeler_fake_fit_diagnostics_and_control_preserve_actual_feedback_across_instances(self):
        self.base.search()  # Disclosed synthetic operator source bootstrap, not a model request.
        self.modeler();one=FakeCloud();first=self.loop.run(one,max_new_requests=1)
        fit=first['study']['actions'][-1]
        self.assertEqual(fit['action'],'fit');self.assertEqual(len(fit['result']['predictions']),32)
        two=FakeCloud();end=C01CloudLoop(self.study.root).run(two,max_new_requests=3)
        context=json.loads(two.requests[0]['messages'][1]['content'])['research_context']
        actual=next(item for item in context['actions'] if item['id']==fit['id'])
        full_metrics={item['target']:item for item in fit['result']['summary']['metrics']}
        self.assertEqual(len(actual['metrics']),4)
        for metric in actual['metrics']:
            self.assertTrue({'target','mae','baseline_mae','better_than_baseline'}<=set(metric))
            self.assertEqual(metric,{key:full_metrics[metric['target']][key] for key in metric})
        self.assertEqual(context['observation_sha256'],first['study']['observation_sha256'])
        self.assertEqual([a['action'] for a in end['study']['actions']],['search','fit','residuals','correlation','stop'])
        self.assertEqual(end['budget']['requests_reserved'],4)
        self.assertFalse(end['scientific_validation']);self.assertEqual(end['tool_profile'],'as_reported_modeler')
        for body in one.requests+two.requests:
            self.assertFalse(self.loop._offered_actions(body)&{'search','read_source','review_evidence'})
        self.assertEqual(C01CloudLoop(self.study.root).run(max_new_requests=0),end)

    def test_cli_omitted_profile_resumes_modeler_with_scripted_transport(self):
        self.base.search();self.modeler()
        class OwnedFake(FakeCloud):
            stopped=False
            key_metadata_unchanged=True
            def __enter__(self):return self
            def __exit__(self,*_):self.stopped=True
        server=OwnedFake()
        args=['cloud-cli','--workspace',str(self.study.root),'--output',str(self.base.root/'cli-modeler'),
              '--model-store','synthetic-unused-store','--max-new-requests','1']
        with patch.object(sys,'argv',args),patch.object(cli,'OwnedCloudOllama',return_value=server):
            self.assertEqual(cli.main(),0)
        self.assertTrue(server.stopped);self.assertEqual(len(server.requests),1)
        self.assertNotIn('search',self.loop._offered_actions(server.requests[0]))
        result=self.loop.status();self.assertEqual(result['tool_profile'],'as_reported_modeler')
        self.assertEqual(result['budget']['requests_reserved'],1)
        self.assertEqual(result['study']['actions'][-1]['action'],'fit')

    def test_cli_explicit_profile_drift_fails_without_starting_transport(self):
        before=self.modeler()
        output=self.base.root/'cli-wrong-profile'
        args=['cloud-cli','--workspace',str(self.study.root),'--output',str(output),
              '--tool-profile','general','--model-store','synthetic-unused-store','--max-new-requests','1']
        with patch.object(sys,'argv',args),patch.object(cli,'OwnedCloudOllama',side_effect=AssertionError('no transport')):
            self.assertEqual(cli.main(),1)
        self.assertEqual(json.loads((output/'failure.json').read_text())['code'],'CONFIG_CHANGED')
        self.assertEqual(self.loop.status(),before)

    def test_cli_omitted_profile_recovers_received_modeler_offline_without_resetting_budget(self):
        self.base.search();self.modeler();server=FakeCloud()
        with patch.object(self.loop,'_consume',side_effect=RuntimeError('after received')):
            with self.assertRaises(RuntimeError):self.loop.run(server,max_new_requests=1)
        before=self.loop.status();args=['cloud-cli','--workspace',str(self.study.root),
             '--output',str(self.base.root/'cli-offline-modeler'),'--max-new-requests','0']
        with patch.object(sys,'argv',args),patch.object(cli,'OwnedCloudOllama',side_effect=AssertionError('offline only')):
            self.assertEqual(cli.main(),0)
        after=self.loop.status();self.assertEqual(after['tool_profile'],'as_reported_modeler')
        self.assertEqual(after['budget'],before['budget']);self.assertEqual(after['calls'][0]['status'],'applied')
        self.assertEqual(len(server.requests),1);self.assertEqual(after['study']['budget']['fits_used'],1)

    def test_reviewed_profile_routes_pending_proposal_to_critic_and_unresolved_review_back_to_actor(self):
        self.base.search();status=self.reviewed();spec=self.saved_spec()
        self.assertEqual(status['permitted_tool_names'],['correlation','fit','inspect_dataset','pause',
                                                       'propose_control','residuals','review_evidence','stop'])
        body=self.loop._request(self.study.observe(),8,[],spec)
        context=json.loads(body['messages'][1]['content'])['research_context']
        self.assertEqual(context['execution_role'],'actor')
        self.assertIn('propose_control',self.loop._offered_actions(body))
        self.assertFalse(self.loop._offered_actions(body)&{'pause','stop','review_evidence'})
        proposal=self.propose()['action'];before=self.study.observe()
        self.assertEqual(before['status'],'active')
        body=self.loop._request(before,7,[],spec);context=json.loads(body['messages'][1]['content'])['research_context']
        self.assertEqual(context['execution_role'],'critic')
        self.assertEqual(self.loop._offered_actions(body),{'review_evidence'})
        self.assertEqual(context['control_review']['proposal_action_id'],proposal['id'])
        self.assertEqual(context['control_review']['proposal_reason'],proposal['reason'])
        self.assertEqual(context['observation_sha256'],before['observation_sha256'])
        field=body['tools'][0]['function']['parameters']['properties']['field']
        self.assertEqual(field['enum'],['control_rationale'])
        evidence=body['tools'][0]['function']['parameters']['properties']['evidence_action_ids']
        self.assertEqual(evidence['items']['enum'],[proposal['id']])
        self.assertEqual((evidence['minItems'],evidence['maxItems']),(1,1))
        self.assertIn('Choose the review status yourself',body['messages'][0]['content'])
        review=self.review()['action'];after=self.study.observe()
        self.assertEqual(after['status'],'active');self.assertFalse(review['result']['scientific_approval'])
        body=self.loop._request(after,6,[],spec);context=json.loads(body['messages'][1]['content'])['research_context']
        self.assertEqual(context['execution_role'],'actor')
        self.assertTrue(context['control_review']['reviewed'])
        self.assertTrue({'pause','stop'}<=self.loop._offered_actions(body))
        self.assertFalse(self.loop._offered_actions(body)&{'propose_control','review_evidence'})

    def test_reviewed_budget_escape_preserves_controls_for_both_request_and_tool_action_limits(self):
        self.base.search();self.reviewed();spec=self.saved_spec();state=self.study.observe()
        for remaining,tool_slots in [(2,5),(1,5),(8,2),(8,1)]:
            observation=copy.deepcopy(state)
            observation['budget']['max_actions']=observation['budget']['actions_used']+tool_slots
            body=self.loop._request(observation,remaining,[],spec)
            context=json.loads(body['messages'][1]['content'])['research_context']
            self.assertEqual(context['execution_role'],'budget_control')
            self.assertTrue({'pause','stop'}<=self.loop._offered_actions(body))
            self.assertNotIn('propose_control',self.loop._offered_actions(body))
            if remaining==1 or tool_slots==1:self.assertEqual(self.loop._offered_actions(body),{'pause','stop'})
        self.propose();pending=self.study.observe()
        critic=self.loop._request(pending,2,[],spec)
        self.assertEqual(self.loop._offered_actions(critic),{'review_evidence'})
        for remaining,tool_slots in [(1,5),(8,1)]:
            observation=copy.deepcopy(pending);observation['budget']['max_actions']=observation['budget']['actions_used']+tool_slots
            body=self.loop._request(observation,remaining,[],spec)
            context=json.loads(body['messages'][1]['content'])['research_context']
            self.assertEqual(context['execution_role'],'budget_control')
            self.assertFalse(context['control_review']['reviewed'])
            self.assertEqual(self.loop._offered_actions(body),{'pause','stop'})

    def test_old_profiles_never_gain_proposal_or_control_review_fields(self):
        self.base.search();self.propose();state=self.study.observe()
        for profile in ['general','as_reported_modeler']:
            loop=C01CloudLoop(self.study.root,tool_profile=profile)
            spec=loop._specification(IDENTITY,state,8);body=loop._request(state,8,[],spec)
            self.assertNotIn('propose_control',loop._offered_actions(body))
            if profile=='general':
                self.assertEqual(body['messages'][0]['content'],SYSTEM_CLOUD)
                review=next(t['function'] for t in body['tools'] if t['function']['name']=='review_evidence')
                self.assertNotIn('control_rationale',review['parameters']['properties']['field']['enum'])
            else:self.assertNotIn('review_evidence',loop._offered_actions(body))

    def test_new_experiment_invalidates_reviewed_control_and_requires_a_new_proposal(self):
        self.base.search();self.propose();self.review();self.reviewed();spec=self.saved_spec()
        old=self.study.observe();self.assertTrue(control_review_state(old)['reviewed'])
        self.base.fit();current=self.study.observe()
        self.assertFalse(control_review_state(current)['current'])
        body=self.loop._request(current,6,[],spec)
        self.assertIn('propose_control',self.loop._offered_actions(body))
        self.assertFalse(self.loop._offered_actions(body)&{'pause','stop','review_evidence'})

    def test_reviewed_profile_reconfigure_drift_does_not_change_stored_policy_or_requests(self):
        before=self.reviewed()
        for profile in ('general','as_reported_modeler'):
            with self.subTest(profile=profile),self.assertRaises(ResearchError) as error:
                C01CloudLoop(self.study.root,tool_profile=profile).configure(copy.deepcopy(IDENTITY),max_requests=8)
            self.assertEqual(error.exception.code,'CONFIG_CHANGED')
        self.assertEqual(self.loop.status(),before)

    def test_reviewed_native_fit_proposal_critique_and_actor_control_use_real_feedback_without_budget_reset(self):
        self.base.search();self.reviewed()
        def policy(context):
            fits=[a for a in context['actions'] if a['action']=='fit']
            if not fits:return c01_model_fixture.decision(context)
            control=context['control_review'];cited=context['known_source_citation_ids'][:1]
            value={'observation_sha256':context['observation_sha256'],'source_citation_ids':cited,
                   'evidence_action_ids':[fits[-1]['id']],'parameters':{}}
            if context['execution_role']=='critic':
                self.assertEqual(control['latest_experiment_id'],fits[-1]['id'])
                self.assertFalse(control['reviewed'])
                return {**value,'action':'review_evidence','reason':'SYNTHETIC critic read the actual current proposal and numerical feedback.',
                        'evidence_action_ids':[control['proposal_action_id'],fits[-1]['id']],
                        'parameters':{'field':'control_rationale','question':'Does the proposed rationale follow?',
                            'finding':f"Synthetic review observed {len(fits[-1]['metrics'])} actual target metrics; no causal conclusion follows automatically.",
                            'status':'unresolved','next_check':'Preserve the actual negative or positive feedback and choose a justified next action.'}}
            if control['reviewed']:
                reviews=[a for a in context['actions'] if a['action']=='review_evidence']
                self.assertIn('4 actual target metrics',reviews[-1]['finding'])
                return {**value,'action':'pause','reason':'SYNTHETIC actor retains the unresolved qualification after seeing the actual critique.'}
            return {**value,'action':'propose_control','reason':'SYNTHETIC original rationale to be evaluated, not an approved cause.',
                    'parameters':{'decision':'pause'}}
        one=FakeCloud(policy=policy);first=self.loop.run(one,max_new_requests=2)
        self.assertEqual(first['study']['status'],'active')
        self.assertEqual([a['action'] for a in first['study']['actions']],['search','fit','propose_control'])
        fit=first['study']['actions'][1];self.assertEqual(len(fit['result']['predictions']),32)
        two=FakeCloud(policy=policy);end=C01CloudLoop(self.study.root).run(two,max_new_requests=2)
        self.assertEqual(end['study']['status'],'paused')
        self.assertEqual([a['action'] for a in end['study']['actions']],['search','fit','propose_control','review_evidence','pause'])
        self.assertEqual(end['budget']['requests_reserved'],4)
        contexts=[json.loads(b['messages'][1]['content'])['research_context'] for b in one.requests+two.requests]
        self.assertEqual([c['execution_role'] for c in contexts],['actor','actor','critic','actor'])
        full={m['target']:m for m in fit['result']['summary']['metrics']}
        for metric in next(a for a in contexts[2]['actions'] if a['action']=='fit')['metrics']:
            self.assertEqual(metric,{key:full[metric['target']][key] for key in metric})
        self.assertEqual(C01CloudLoop(self.study.root).run(max_new_requests=0),end)

    def test_critic_received_response_recovers_offline_with_saved_role_and_request_count(self):
        self.base.search();self.propose();self.reviewed();server=FakeCloud(policy=scripted_control_review)
        with patch.object(self.loop,'_consume',side_effect=RuntimeError('after critic received')):
            with self.assertRaises(RuntimeError):self.loop.run(server,max_new_requests=1)
        before=self.loop.status();self.assertEqual(before['calls'][0]['status'],'received')
        self.assertFalse(control_review_state(before['study'])['reviewed'])
        with patch.object(C01CloudLoop,'_request',side_effect=AssertionError('saved body only')):
            end=C01CloudLoop(self.study.root).run(max_new_requests=0)
        self.assertTrue(control_review_state(end['study'])['reviewed'])
        self.assertEqual(end['budget'],before['budget']);self.assertEqual(end['calls'][0]['status'],'applied')
        self.assertEqual(len(server.requests),1);self.assertEqual(end['study']['status'],'active')

    def test_critic_post_commit_crash_recovers_saved_role_schema_without_second_review(self):
        self.base.search();self.propose();self.reviewed()
        def critic(context):
            control=context['control_review']
            return {'action':'review_evidence','observation_sha256':context['observation_sha256'],
                'reason':'SYNTHETIC critique only, no approved scientific conclusion.',
                'source_citation_ids':context['known_source_citation_ids'][:1],
                'evidence_action_ids':[control['proposal_action_id']],
                'parameters':{'field':'control_rationale','question':'Is the synthetic rationale supported?',
                    'finding':'No scientific validation is established by this fixture.','status':'unresolved',
                    'next_check':'Let the next actor consider the original evidence.'}}
        server=FakeCloud(policy=critic)
        with patch.object(self.loop,'_record_applied',side_effect=RuntimeError('after critic tool commit')):
            with self.assertRaises(RuntimeError):self.loop.run(server,max_new_requests=1)
        before=self.study.observe();review=before['actions'][-1]
        self.assertEqual(review['action'],'review_evidence');self.assertEqual(before['status'],'active')
        with self.loop._connect() as con:
            saved=json.loads(con.execute('SELECT request_json FROM calls').fetchone()[0])
        self.assertEqual(self.loop._offered_actions(saved),{'review_evidence'})
        with patch.object(C01CloudLoop,'_request',side_effect=AssertionError('must use saved request')):
            end=C01CloudLoop(self.study.root).run(max_new_requests=0)
        self.assertEqual(end['study'],before);self.assertEqual(end['calls'][0]['action_id'],review['id'])
        self.assertEqual(end['calls'][0]['status'],'applied');self.assertEqual(end['budget']['requests_reserved'],1)
        self.assertEqual(len(server.requests),1)

    def test_critic_cannot_dispatch_an_actor_control_from_its_saved_tool_table(self):
        self.base.search();self.propose();self.reviewed()
        def actor_control(context):
            return {'action':'pause','reason':'SYNTHETIC wrong-role request.',
                    'observation_sha256':context['observation_sha256'],'source_citation_ids':[],
                    'evidence_action_ids':[],'parameters':{}}
        result=self.loop.run(FakeCloud(policy=actor_control),max_new_requests=1)
        self.assertEqual(result['calls'][0]['error_code'],'ACTION_NOT_AVAILABLE')
        self.assertEqual(result['study']['status'],'active')
        self.assertFalse(control_review_state(result['study'])['reviewed'])

    def test_critic_retries_share_the_same_eight_request_cap_and_final_unreviewed_control_is_not_approval(self):
        self.base.search();self.reviewed()
        def policy(context):
            if context['execution_role']=='critic':return 'SYNTHETIC invalid response; no tool call.'
            return {'action':'propose_control' if context['remaining_model_requests']>=3 else 'pause',
                    'reason':'SYNTHETIC bounded control; no scientific approval.',
                    'observation_sha256':context['observation_sha256'],
                    'source_citation_ids':context['known_source_citation_ids'][:1],
                    'evidence_action_ids':[],
                    'parameters':{'decision':'pause'} if context['remaining_model_requests']>=3 else {}}
        one=FakeCloud(policy=policy);first=self.loop.run(one,max_new_requests=4)
        self.assertEqual(first['budget']['requests_reserved'],4)
        two=FakeCloud(policy=policy);end=C01CloudLoop(self.study.root).run(two,max_new_requests=8)
        self.assertEqual(end['budget']['requests_reserved'],8);self.assertEqual(len(one.requests)+len(two.requests),8)
        self.assertEqual(end['study']['status'],'paused')
        self.assertEqual(sum(c['status']=='invalid' for c in end['calls']),6)
        final=json.loads(two.requests[-1]['messages'][1]['content'])['research_context']
        self.assertEqual(final['execution_role'],'budget_control');self.assertFalse(final['control_review']['reviewed'])
        self.assertEqual(self.loop._offered_actions(two.requests[-1]),{'pause','stop'})

    def test_same_research_tools_actual_feedback_and_cross_instance_request_limit(self):
        self.configure();one=FakeCloud()
        first=self.loop.run(one,max_new_requests=2)
        self.assertEqual([a['action'] for a in first['study']['actions']],['search','fit'])
        second_loop=C01CloudLoop(self.study.root);second_loop.configure(copy.deepcopy(IDENTITY),max_requests=8)
        two=FakeCloud();end=second_loop.run(two,max_new_requests=6)
        self.assertEqual([a['action'] for a in end['study']['actions']],['search','fit','residuals','correlation','stop'])
        self.assertEqual(end['budget']['requests_reserved'],5)
        self.assertEqual(one.budgets,[8]);self.assertEqual(two.budgets,[6])
        self.assertEqual(end['cloud_calls'],5);self.assertIsNone(end['actual_inference_cash_cny'])
        self.assertFalse(end['scientific_validation']);self.assertFalse(end['local_model_weights_verified'])
        self.assertFalse((self.study.root/'local-model.sqlite').exists())
        self.assertEqual(len(end['study']['actions'][1]['result']['predictions']),32)
        self.assertEqual(C01CloudLoop(self.study.root).run(max_new_requests=0),end)

    def test_saved_request_is_exact_cloud_body_and_references_are_not_prefix_480(self):
        self.base.search();self.configure()
        # A full quote available in the real observation, not a provider-invented excerpt.
        observation=self.study.observe();spec=self.loop._specification(IDENTITY,observation,8)
        projected=copy.deepcopy(observation);projected['citations'][0]['quote']='x'*1300
        body=self.loop._request(projected,8,[],spec)
        context=json.loads(body['messages'][1]['content'])['research_context']
        self.assertEqual(len(context['references'][0]['quote']),1300)
        self.assertEqual(body['options']['num_ctx'],32768);self.assertNotIn('format',body)
        self.assertEqual(body['think'],spec['reasoning_effort']);self.assertEqual(body['think'],'medium')
        def durable(sent):
            with self.loop._connect() as con:
                row=con.execute('SELECT * FROM calls').fetchone()
                self.assertEqual(row['status'],'sending');self.assertEqual(row['request_sha256'],fingerprint(sent))
                self.assertEqual(json.loads(row['request_json']),sent)
        self.loop.run(FakeCloud(before=durable),max_new_requests=1)

    def test_received_response_recovers_offline_without_account_or_second_send(self):
        self.configure();server=FakeCloud()
        with patch.object(self.loop,'_consume',side_effect=RuntimeError('simulated post-receive crash')):
            with self.assertRaises(RuntimeError):self.loop.run(server,max_new_requests=1)
        self.assertEqual(self.loop.status()['calls'][0]['status'],'received')
        end=C01CloudLoop(self.study.root).run(max_new_requests=0)
        self.assertEqual(end['calls'][0]['status'],'applied');self.assertEqual(len(server.requests),1)
        self.assertEqual(len(end['study']['actions']),1)

    def test_read_feedback_reaches_a_new_controller_instance_before_its_actual_fixture_fit(self):
        self.configure();first=self.loop.run(FakeCloud(policy=scripted_read),max_new_requests=1)
        self.assertEqual([a['action'] for a in first['study']['actions']],['read_source'])
        quote=first['study']['citations'][0]['quote'];card=first['study']['source_catalogue']['documents'][0]
        second_server=FakeCloud();second=C01CloudLoop(self.study.root).run(second_server,max_new_requests=1)
        context=json.loads(second_server.requests[0]['messages'][1]['content'])['research_context']
        self.assertEqual(context['references'][0]['quote'],quote)
        self.assertEqual(context['references'][0]['document_id'],card['document_id'])
        self.assertEqual(context['reading_navigation']['window']['source_sha256'],card['source_sha256'])
        self.assertEqual(context['research_progress']['executed_read_windows'][0]['new_citations'],1)
        self.assertEqual([a['action'] for a in second['study']['actions']],['read_source','fit'])
        self.assertEqual(second['budget']['requests_reserved'],2)
        self.assertEqual(len(second['study']['actions'][1]['result']['predictions']),32)

    def test_read_tool_commit_recovers_same_citations_without_rereading_or_new_native_call(self):
        self.configure();server=FakeCloud(policy=scripted_read)
        with patch.object(self.loop,'_record_applied',side_effect=RuntimeError('synthetic after readcommit')):
            with self.assertRaises(RuntimeError):self.loop.run(server,max_new_requests=1)
        before=self.study.observe();self.assertEqual(len(before['actions']),1)
        with patch('autoresearch.c01_research.KnowledgeIndex.read_source',side_effect=AssertionError('must replay old read')):
            end=C01CloudLoop(self.study.root).run(max_new_requests=0)
        self.assertEqual(end['study'],before)
        self.assertEqual(end['calls'][0]['status'],'applied');self.assertEqual(len(server.requests),1)

    def test_inspection_values_and_hashes_reach_next_controller_instance_without_scientific_approval(self):
        self.inspection_study()
        def inspect(context):
            return {'action':'inspect_dataset', 'observation_sha256':context['observation_sha256'],
                    'reason':'SYNTHETIC inspect contract; not model research.',
                    'source_citation_ids':[], 'evidence_action_ids':[], 'parameters':{}}
        self.configure(); first=self.loop.run(FakeCloud(policy=inspect), max_new_requests=1)
        action=first['study']['actions'][0]
        self.assertEqual(action['action'],'inspect_dataset')
        def search(context):
            projected=context['dataset_inspection']
            self.assertEqual(projected['action_id'],action['id'])
            self.assertEqual(projected['result_sha256'],action['result_sha256'])
            self.assertTrue(projected['projection_not_full_result'])
            recovered=copy.deepcopy(projected['projection']);table=recovered.pop('provenance_table')
            recovered['provenance']=[dict(zip(table['columns'],row)) for row in table['rows']]
            self.assertEqual(recovered,action['result'])
            self.assertFalse(recovered['scientific_approval'])
            self.assertEqual(len(recovered['samples']),8)
            self.assertEqual(len(recovered['provenance']),64)
            return {**inspect(context),'action':'search','parameters':{'query':'C01 alloy'}}
        server=FakeCloud(policy=search)
        second=C01CloudLoop(self.study.root).run(server,max_new_requests=1)
        self.assertEqual([a['action'] for a in second['study']['actions']],['inspect_dataset','search'])
        self.assertEqual(second['budget']['requests_reserved'],2)
        self.assertEqual(C01CloudLoop(self.study.root).run(max_new_requests=0),second)

    def test_committed_inspection_recovers_without_reinspection_or_new_model_request(self):
        self.inspection_study()
        def inspect(context):
            return {'action':'inspect_dataset','observation_sha256':context['observation_sha256'],
                    'reason':'SYNTHETIC crash recovery only.','source_citation_ids':[],
                    'evidence_action_ids':[],'parameters':{}}
        self.configure();server=FakeCloud(policy=inspect)
        with patch.object(self.loop,'_record_applied',side_effect=RuntimeError('synthetic after inspectcommit')):
            with self.assertRaises(RuntimeError):self.loop.run(server,max_new_requests=1)
        before=self.study.observe()
        self.assertEqual(len(before['actions']),1)
        with patch.object(type(self.study),'_inspect_dataset',side_effect=AssertionError('must replay original inspection')):
            end=C01CloudLoop(self.study.root).run(max_new_requests=0)
        self.assertEqual(end['study'],before)
        self.assertEqual(end['calls'][0]['status'],'applied');self.assertEqual(len(server.requests),1)

    def test_reference_catalogue_preserves_existing_roles_without_rewriting_quotes_or_guessing_approval(self):
        self.base.search();self.configure();observation=self.study.observe()
        with self.loop._connect() as con:spec=json.loads(con.execute('SELECT spec_json FROM project').fetchone()[0])
        projected=copy.deepcopy(observation);quote=projected['citations'][0]['quote']
        projected['citations'][0]['source']['metadata']={'doi':'10.synthetic/related','source_role':'primary_related_paper_not_c01_holdout',
            'applicability':'Synthetic different substrate/cell conditions.','title_role':'operator catalogue label',
            'manual_protocol_review_included':False,'unrelated_secret_field':'NEVER_PROJECT_ME'}
        before=copy.deepcopy(projected)
        body=self.loop._request(projected,8,[],spec)
        reference=json.loads(body['messages'][1]['content'])['research_context']['references'][0]
        catalogue=reference['source_catalogue']
        self.assertEqual(reference['quote'],quote);self.assertEqual(projected,before)
        for key in ('doi','source_role','applicability','title_role','manual_protocol_review_included'):
            self.assertEqual(catalogue[key],projected['citations'][0]['source']['metadata'][key])
        self.assertNotIn('NEVER_PROJECT_ME',canonical(body));self.assertFalse(catalogue['manual_protocol_review_included'])
        projected['citations'][0]['source']['metadata']={'applicability':'x'*501,'manual_protocol_review_included':'true'}
        body=self.loop._request(projected,8,[],spec)
        catalogue=json.loads(body['messages'][1]['content'])['research_context']['references'][0]['source_catalogue']
        self.assertEqual(len(catalogue['applicability']),500);self.assertEqual(catalogue['truncated_fields'],['applicability'])
        self.assertNotIn('source_role',catalogue);self.assertNotIn('manual_protocol_review_included',catalogue)

    def test_inventory_is_bound_to_this_frozen_index_and_only_nonempty_categories_are_offered(self):
        status=self.configure();observation=status['study']
        with self.loop._connect() as con:spec=json.loads(con.execute('SELECT spec_json FROM project').fetchone()[0])
        manifest=json.loads(self.base.index.with_suffix('.json').read_text(encoding='utf-8'))
        inventory=spec['knowledge_inventory']
        self.assertEqual(inventory['database_sha256'],manifest['database_sha256'])
        self.assertEqual(inventory['corpus_sha256'],manifest['corpus_sha256'])
        self.assertEqual(inventory['documents_by_kind'],{'reuse_note':1})
        self.assertEqual(inventory['indexed_documents'],manifest['documents'])
        self.assertEqual(inventory['indexed_chunks'],manifest['chunks'])
        body=self.loop._request(observation,8,[],spec)
        context=json.loads(body['messages'][1]['content'])['research_context']
        self.assertEqual(context['knowledge_inventory'],inventory)
        tool=next(x['function'] for x in body['tools'] if x['function']['name']=='search')
        field=tool['parameters']['properties']['kinds']
        self.assertEqual(field['items']['enum'],['reuse_note']);self.assertEqual(field['maxItems'],1)
        self.assertNotIn('kinds',tool['parameters']['required'])
        self.assertNotIn('limit',tool['parameters']['required'])
        self.assertEqual(C01CloudLoop(self.study.root).configure(copy.deepcopy(IDENTITY),max_requests=8),status)

    def test_absent_index_category_is_rejected_without_repair_or_search_and_omission_still_searches_all(self):
        self.configure()
        def absent(context):
            choice=c01_model_fixture.decision(context);choice['parameters']['kinds']=['official_doc'];return choice
        rejected=self.loop.run(FakeCloud(policy=absent),max_new_requests=1)
        self.assertEqual(rejected['calls'][0]['error_code'],'INVALID_SEARCH_KIND')
        self.assertEqual(rejected['study']['actions'],[])
        def omit(context):
            choice=c01_model_fixture.decision(context);choice['parameters'].pop('kinds',None);return choice
        server=FakeCloud(policy=omit);accepted=C01CloudLoop(self.study.root).run(server,max_new_requests=1)
        self.assertEqual(len(accepted['study']['citations']),1)
        self.assertNotIn('kinds',accepted['study']['actions'][0]['parameters'])
        context=json.loads(server.requests[0]['messages'][1]['content'])['research_context']
        self.assertIn('offered',context['previous_errors'][0]['message'])

    def test_unknown_send_locks_cross_process_even_with_new_server(self):
        self.configure()
        def unknown(_):raise ResearchError('CLOUD_REQUEST_UNKNOWN','simulated unknown')
        one=FakeCloud(before=unknown)
        with self.assertRaises(ResearchError):self.loop.run(one,max_new_requests=1)
        new=FakeCloud()
        with self.assertRaises(ResearchError) as error:C01CloudLoop(self.study.root).run(new,max_new_requests=8)
        self.assertEqual(error.exception.code,'NEEDS_REVIEW');self.assertEqual(new.requests,[])
        self.assertTrue(self.loop.status()['unknown_cloud_send']);self.assertEqual(len(one.requests),1)

    def test_cloud_identity_period_and_cumulative_budget_are_frozen_before_send(self):
        self.configure(3)
        with self.assertRaises(ResearchError):self.loop.configure(copy.deepcopy(IDENTITY),max_requests=4)
        changed=copy.deepcopy(IDENTITY);changed['account_period']['until']='2026-12-18T00:00:00Z'
        server=FakeCloud(identity=changed)
        with self.assertRaises(ResearchError) as error:self.loop.run(server,max_new_requests=1)
        self.assertEqual(error.exception.code,'MODEL_CHANGED');self.assertEqual(server.requests,[])
        self.assertEqual(self.loop.status()['budget']['requests_reserved'],0)

    def test_textual_json_is_not_repaired_into_a_native_tool_call(self):
        self.configure(2)
        result=self.loop.run(FakeCloud(policy=lambda _:'```json\n{}\n```'),max_new_requests=1)
        self.assertEqual(result['calls'][0]['error_code'],'MISSING_TOOL_CALL')
        self.assertEqual(result['calls'][0]['status'],'invalid');self.assertEqual(result['study']['actions'],[])
        self.assertEqual(result['budget']['requests_reserved'],1)

    def test_native_validation_feedback_reaches_next_model_request(self):
        self.configure(3)
        self.loop.run(FakeCloud(policy=lambda _:'{}'),max_new_requests=1)
        server=FakeCloud();self.loop.run(server,max_new_requests=1)
        context=json.loads(server.requests[0]['messages'][1]['content'])['research_context']
        self.assertEqual(context['previous_errors'][0]['code'],'MISSING_TOOL_CALL')
        self.assertIn('exactly one',context['previous_errors'][0]['message'])

    def test_credit_preflight_fails_before_model_reservation_and_is_retryable_without_dispatch(self):
        self.configure();server=FakeCloud()
        with patch.object(server,'prepare',side_effect=ResearchError('QUOTA_UNKNOWN','synthetic metadata error')):
            with self.assertRaises(ResearchError):self.loop.run(server,max_new_requests=1)
        before=self.loop.status()
        self.assertEqual(before['budget']['requests_reserved'],0);self.assertEqual(before['status'],'active')
        self.assertEqual(server.requests,[])
        after=C01CloudLoop(self.study.root).run(FakeCloud(),max_new_requests=1)
        self.assertEqual(after['budget']['requests_reserved'],1)

    def test_specific_search_limit_feedback_survives_restart_without_repairing_rejected_choice(self):
        self.configure()
        def invalid_limit(context):
            choice=c01_model_fixture.decision(context);choice['parameters']['limit']=5
            return choice
        first=self.loop.run(FakeCloud(policy=invalid_limit),max_new_requests=1)
        self.assertEqual(first['calls'][0]['error_code'],'INVALID_SEARCH_LIMIT')
        self.assertEqual(first['study']['actions'],[])
        server=FakeCloud();second=C01CloudLoop(self.study.root).run(server,max_new_requests=1)
        context=json.loads(server.requests[0]['messages'][1]['content'])['research_context']
        feedback=context['previous_errors'][0]
        self.assertEqual(feedback['code'],'INVALID_SEARCH_LIMIT')
        self.assertIn('1 through 4',feedback['message'])
        self.assertEqual(second['budget']['requests_reserved'],2)
        self.assertEqual([a['action'] for a in second['study']['actions']],['search'])
        with self.loop._connect() as con:
            saved=json.loads(con.execute('SELECT response_json FROM calls WHERE ordinal=1').fetchone()[0])
        self.assertEqual(saved['message']['tool_calls'][0]['function']['arguments']['limit'],5)

    def test_received_response_is_consumed_and_credit_hold_blocks_further_model_calls(self):
        self.configure();server=FakeCloud()
        def hold(_):server.credit_hold={'code':'QUOTA_UNKNOWN','response_received':True}
        server.before=hold
        result=self.loop.run(server,max_new_requests=8)
        self.assertEqual(len(server.requests),1);self.assertEqual(result['calls'][0]['status'],'applied')
        self.assertEqual(result['status'],'needs_review')
        self.assertEqual(result['reason'],'CLOUD_CREDIT_RECONCILIATION_REQUIRED')
        self.assertEqual(result['study']['status'],'active');self.assertFalse(result['unknown_cloud_send'])
        self.assertEqual(C01CloudLoop(self.study.root).run(max_new_requests=0),result)

    def test_credit_hold_is_atomic_with_received_before_crash_and_survives_offline_consumption(self):
        self.configure();server=FakeCloud()
        def hold(_):server.credit_hold={'code':'QUOTA_UNKNOWN','response_received':True}
        server.before=hold
        with patch.object(self.loop,'_consume',side_effect=RuntimeError('after receipt before consumption')):
            with self.assertRaises(RuntimeError):self.loop.run(server,max_new_requests=1)
        saved=self.loop.status()
        self.assertEqual(saved['calls'][0]['status'],'received');self.assertEqual(saved['status'],'needs_review')
        recovered=C01CloudLoop(self.study.root).run(max_new_requests=0)
        self.assertEqual(recovered['calls'][0]['status'],'applied')
        self.assertEqual(recovered['status'],'needs_review');self.assertEqual(recovered['reason'],'CLOUD_CREDIT_RECONCILIATION_REQUIRED')
        new=FakeCloud();self.assertEqual(C01CloudLoop(self.study.root).run(new,max_new_requests=8),recovered)
        self.assertEqual(new.requests,[]);self.assertEqual(len(server.requests),1)

    def test_terminal_schema_saved_and_enforced_without_format_api(self):
        self.configure(1)
        result=self.loop.run(FakeCloud(),max_new_requests=1)  # Fixture attempts search, unavailable in final slot.
        self.assertEqual(result['calls'][0]['error_code'],'ACTION_NOT_AVAILABLE')
        self.assertEqual(result['study']['actions'],[])
        self.assertEqual(result['reason'],'REQUEST_LIMIT')

    def test_tool_commit_interruption_recovers_same_fit_id_without_refitting(self):
        self.configure();self.loop.run(FakeCloud(),max_new_requests=1)
        with patch.object(self.loop,'_record_applied',side_effect=RuntimeError('after tool commit')):
            with self.assertRaises(RuntimeError):self.loop.run(FakeCloud(),max_new_requests=1)
        before=self.study.observe();self.assertEqual(before['budget']['fits_used'],1)
        with patch('autoresearch.c01_research.C01Research._execute',side_effect=AssertionError('must replay')):
            end=C01CloudLoop(self.study.root).run(max_new_requests=0)
        self.assertEqual(end['study'],before);self.assertEqual(end['calls'][-1]['status'],'applied')

    def test_latest_diagnostic_error_and_committed_recovery_use_saved_feedback_not_fresh_state(self):
        self.base.search();fit=self.base.fit()['action']
        residual=self.study.apply(self.base.request('residuals',{'fit_action_id':fit['id']}))['action']
        self.configure()
        def choose(context,ids):
            return {'action':'correlation','observation_sha256':context['observation_sha256'],
                    'reason':'Synthetic feedback-binding test, not a real research choice.',
                    'source_citation_ids':context['known_source_citation_ids'][:1],
                    'evidence_action_ids':ids,'parameters':{}}
        old=FakeCloud(policy=lambda ctx:choose(ctx,[fit['id']]))
        first=self.loop.run(old,max_new_requests=1)
        self.assertEqual(first['calls'][-1]['error_code'],'LATEST_FEEDBACK_REQUIRED')
        self.assertEqual(first['study']['actions'][-1]['id'],residual['id'])
        correct=FakeCloud(policy=lambda ctx:choose(ctx,[ctx['feedback_binding']['action_id']]))
        with patch.object(self.loop,'_record_applied',side_effect=RuntimeError('synthetic after diagnostic commit')):
            with self.assertRaises(RuntimeError):self.loop.run(correct,max_new_requests=1)
        context=json.loads(correct.requests[0]['messages'][1]['content'])['research_context']
        self.assertEqual(context['feedback_binding'],{
            'action_id':residual['id'],'action':'residuals','action_ordinal':residual['ordinal'],
            'result_sha256':residual['result_sha256'],
            'required_for_actions':['correlation','fit','propose_control','residuals'],
            'rule':context['feedback_binding']['rule']})
        self.assertEqual(context['previous_errors'][0]['code'],'LATEST_FEEDBACK_REQUIRED')
        before=self.study.observe();self.assertEqual(before['actions'][-1]['action'],'correlation')
        with patch('autoresearch.c01_research.C01Research._execute',side_effect=AssertionError('must replay saved diagnostic')):
            end=C01CloudLoop(self.study.root).run(max_new_requests=0)
        self.assertEqual(end['study'],before);self.assertEqual(end['calls'][-1]['status'],'applied')
        self.assertEqual(len(old.requests)+len(correct.requests),2)

    def test_cli_offline_recovery_does_not_start_transport_or_need_model_store(self):
        self.configure();server=FakeCloud()
        with patch.object(self.loop,'_consume',side_effect=RuntimeError('after received')):
            with self.assertRaises(RuntimeError):self.loop.run(server,max_new_requests=1)
        args=['cloud-cli','--workspace',str(self.study.root),'--output',str(self.base.root/'offline'),
              '--max-new-requests','0']
        with patch.object(sys,'argv',args),patch.object(cli,'OwnedCloudOllama',side_effect=AssertionError('offline')):
            self.assertEqual(cli.main(),0)
        self.assertEqual(C01CloudLoop(self.study.root).status()['calls'][0]['status'],'applied')

    def test_local_default_remains_an_independent_model_and_journal(self):
        local=C01LocalLoop(self.study.root)
        self.assertEqual(local.db.name,'local-model.sqlite');self.assertNotEqual(local.db,self.loop.db)
        with self.assertRaises(ResearchError):local.configure(copy.deepcopy(IDENTITY))
        self.assertFalse(local.db.exists())


if __name__=='__main__':unittest.main()
