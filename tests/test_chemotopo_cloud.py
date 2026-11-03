import copy
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import chemotopo_cloud as module
from autoresearch import c01_native_tools, ollama_cloud
from autoresearch.contracts import ResearchError, canonical
from autoresearch.research_memory import ResearchMemory
from test_chemotopo_study import fixture_environment, request


IDENTITY={'model':ollama_cloud.MODEL,'remote_model':ollama_cloud.REMOTE_MODEL,'remote_host':ollama_cloud.REMOTE_HOST,
          'alias_sha256':ollama_cloud.ALIAS_SHA256,'config_sha256':ollama_cloud.CONFIG_SHA256,
          'account_identity_sha256':'a'*64,'account_period':{'from':'fixture-from','until':'fixture-until'}}


def response(body,action):
    context=json.loads(body['messages'][1]['content'])
    relevant=[a['id'] for a in context['actions'] if a['action'] in {'inspect_source','compare_policies'}]
    args={'observation_sha256':context['observation_sha256'],'reason':'Scripted fixture, not actual model research.',
          'source_citation_ids':[r['citation_id'] for r in context['current_citations']],
          'evidence_action_ids':relevant[-1:]}
    if action=='review_evidence':args.update(field='zero_policy',finding='Proxy sensitivity is conditional, not ALP evidence.',status='unresolved',next_check='Original channel/export/zero mapping')
    return {'model':ollama_cloud.REMOTE_MODEL,'done':True,'prompt_eval_count':100,'eval_count':50,
            'message':{'role':'assistant','content':'','tool_calls':[{'type':'function','function':{'name':action,'arguments':args}}]}}


class ServerFixture:
    def __init__(self,actions,fail=False):
        self.actions=iter(actions);self.bodies=[];self.prepared=[];self.credit_hold=None;self.fail=fail
        self.http=SimpleNamespace(request=self.call)
    def assert_owner(self):pass
    def acquire(self):return copy.deepcopy(IDENTITY)
    def configure_budget(self,identity,remaining):self.remaining=remaining
    def prepare(self,body):self.prepared.append(copy.deepcopy(body))
    def call(self,route,body,timeout):
        self.bodies.append(copy.deepcopy(body))
        if self.fail:raise OSError('fixture unknown outcome')
        return response(body,next(self.actions))


class ChemoTopoCloudTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        context=fixture_environment();context.__enter__();self.addCleanup(context.__exit__,None,None,None)
        self.root=Path(self.directory.name)/'study';self.loop=module.ChemoTopoCloudLoop(self.root)
        self.loop.study.create('fixture-source','Evaluate source policies and conditional memory, not ALP.')
        self.loop.configure(IDENTITY,max_requests=8)

    def test_fixture_flow_uses_shared_journal_and_actual_persistent_memory_snapshot(self):
        server=ServerFixture(['inspect_source','compare_policies','remember_evidence','recall_evidence','check_training_gate','review_evidence','pause'])
        result=self.loop.run(server,max_new_requests=8,verified_weights=IDENTITY)
        self.assertEqual(result['status'],'completed');self.assertEqual(result['study']['status'],'paused');self.assertEqual(len(server.bodies),7)
        self.assertEqual(result['study']['budget']['fits_used'],0)
        self.assertEqual(len(result['study']['memory_context']['entries']),2)
        for body in server.bodies[3:]:
            context=json.loads(body['messages'][1]['content']);self.assertEqual(len(context['memory_context']['entries']),2)
        first=json.loads(server.bodies[0]['messages'][1]['content'])
        self.assertIn('all-zero groups',first['zero_record_semantics'])
        self.assertEqual(len(first['fixed_policy_names']),4)
        compared=json.loads(server.bodies[2]['messages'][1]['content'])['actions'][-1]['result']
        self.assertIn('control',compared['protocol'])
        self.assertEqual(compared['policies']['recorded_equal_batch']['batch_coverage_counts']['3'],2)
        self.assertIn('control',compared['policies']['positive_equal_batch']['source_control_examples'][0])
        with self.loop._connect() as con:
            rows=con.execute('SELECT observation_json,request_json,status FROM calls ORDER BY ordinal').fetchall()
            for row in rows:
                snapshot=json.loads(row['observation_json'])['memory_context']
                actual=json.loads(json.loads(row['request_json'])['messages'][1]['content'])['memory_context']
                self.assertEqual(snapshot,actual);self.assertEqual(row['status'],'applied')
        self.assertEqual(self.loop.run(max_new_requests=0)['budget']['requests_reserved'],7)

    def test_unoffered_fit_and_parameter_bag_are_rejected_without_dispatch(self):
        state=self.loop.study.observe()
        with self.loop._connect() as con:_,spec,_=self.loop._state(con)
        body=self.loop._request(state,8,[],spec)
        forged=response(body,'fit')
        with self.assertRaises(ResearchError) as error:self.loop._parse_decision(forged,state,'fixture',body)
        self.assertEqual(error.exception.code,'ACTION_NOT_AVAILABLE')
        forged=response(body,'inspect_source');forged['message']['tool_calls'][0]['function']['arguments']['parameters']={}
        with self.assertRaises(ResearchError):self.loop._parse_decision(forged,state,'fixture',body)
        self.assertEqual(self.loop.study.observe()['actions'],[])

    def test_unknown_send_stays_reserved_and_is_not_retried(self):
        server=ServerFixture([],fail=True)
        with self.assertRaises(ResearchError) as error:self.loop.run(server,max_new_requests=1,verified_weights=IDENTITY)
        self.assertEqual(error.exception.code,'NEEDS_REVIEW')
        self.assertEqual(self.loop.status()['calls'][0]['status'],'sending')
        with self.assertRaises(ResearchError):self.loop.run(max_new_requests=0)
        self.assertEqual(len(server.bodies),1)

    def test_withdrawal_invalidates_received_but_uncommitted_decision(self):
        self.loop.run(ServerFixture(['inspect_source','compare_policies','remember_evidence']),max_new_requests=3,verified_weights=IDENTITY)
        state=self.loop.study.observe()
        with self.loop._connect() as con:_,spec,_=self.loop._state(con)
        body=self.loop._request(state,5,[],spec);call_id,request_id=self.loop._reserve(state,body)
        self.loop._received(call_id,response(body,'check_training_gate'))
        entry=state['memory_context']['entries'][0]['id']
        ResearchMemory(self.root/'observation-memory').set_status(entry,'retired','Withdraw pending context','withdraw')
        result=module.ChemoTopoCloudLoop(self.root).run(max_new_requests=0)
        self.assertEqual(result['calls'][-1]['status'],'invalid')
        self.assertEqual(result['calls'][-1]['error_code'],'STALE_OBSERVATION')
        self.assertEqual(len(result['study']['actions']),3)

    def test_cross_process_received_recovery_after_memory_action_commit_no_inference(self):
        server=ServerFixture(['inspect_source','compare_policies','remember_evidence'])
        self.loop.run(server,max_new_requests=2,verified_weights=IDENTITY)
        with patch.object(self.loop,'_record_applied',side_effect=RuntimeError('crash after study and memory commit')):
            with self.assertRaises(RuntimeError):self.loop.run(server,max_new_requests=1,verified_weights=IDENTITY)
        before=self.loop.status();self.assertEqual(before['calls'][-1]['status'],'received')
        entry=before['study']['memory_context']['entries'][0]['id']
        ResearchMemory(self.root/'observation-memory').set_status(entry,'retired','Preserve withdrawal during replay','retire')
        env=dict(os.environ);env['PYTHONPATH']=os.pathsep.join([str(Path(__file__).parent),str(Path(__file__).parents[1]/'src')])
        code='from test_chemotopo_study import fixture_environment;from autoresearch.chemotopo_cloud import ChemoTopoCloudLoop;import json,sys\nwith fixture_environment():\n r=ChemoTopoCloudLoop(sys.argv[1]).run(max_new_requests=0);print(json.dumps({"calls":r["budget"]["requests_reserved"],"last":r["calls"][-1]["status"],"actions":len(r["study"]["actions"]),"memory":len(r["study"]["memory_context"]["entries"])}))'
        child=subprocess.run([sys.executable,'-c',code,str(self.root)],env=env,capture_output=True,text=True,timeout=30)
        self.assertEqual(child.returncode,0,child.stderr)
        self.assertEqual(json.loads(child.stdout),{'calls':3,'last':'applied','actions':3,'memory':1})
        self.assertEqual(len(server.bodies),3)

    def test_body_tamper_is_not_consumed_as_valid_feedback(self):
        state=self.loop.study.observe()
        with self.loop._connect() as con:_,spec,_=self.loop._state(con)
        body=self.loop._request(state,8,[],spec);cid,_=self.loop._reserve(state,body);self.loop._received(cid,response(body,'inspect_source'))
        with self.loop._connect(True) as con:con.execute('UPDATE calls SET request_json=? WHERE id=?',(canonical({**body,'keep_alive':999}),cid))
        with self.assertRaises(ResearchError) as error:self.loop.run(max_new_requests=0)
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')
        self.assertEqual(self.loop.study.observe()['actions'],[])

    def test_terminal_schema_and_context_cap_are_enforced_before_reservation(self):
        state=self.loop.study.observe()
        with self.loop._connect() as con:_,spec,_=self.loop._state(con)
        terminal=self.loop._request(state,1,[],spec)
        self.assertEqual({t['function']['name'] for t in terminal['tools']},{'pause','stop'})
        with patch.object(module,'SYSTEM','x'*70000):
            with self.assertRaises(ResearchError):self.loop._request(state,8,[],spec)
        self.assertEqual(self.loop.status()['budget']['requests_reserved'],0)

    def test_cli_invalid_budget_never_starts_transport_or_creates_output(self):
        script=Path(__file__).parents[1]/'scripts/run_chemotopo_research.py'
        for flag,value in [('--max-requests','0'),('--max-requests','9'),('--max-new-requests','-1'),('--max-new-requests','9')]:
            output=Path(self.directory.name)/('invalid-'+flag+'-'+value)
            child=subprocess.run([sys.executable,str(script),'--workspace',str(self.root),'--output',str(output),flag,value],capture_output=True,text=True,timeout=20)
            self.assertEqual(child.returncode,2)
            self.assertFalse(output.exists())

    def test_terminal_cli_is_offline_and_does_not_construct_a_transport(self):
        self.loop.study.apply(request(self.loop.study,'pause','pause'))
        script=Path(__file__).parents[1]/'scripts/run_chemotopo_research.py'
        spec=importlib.util.spec_from_file_location('p02_cli_fixture',script);cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
        output=Path(self.directory.name)/'offline'
        args=['cli','--workspace',str(self.root),'--output',str(output),'--max-new-requests','0']
        class Output(io.StringIO):
            def reconfigure(self,**kwargs):pass
        with patch.object(sys,'argv',args),patch.object(cli,'OwnedCloudOllama',side_effect=AssertionError('offline terminal must not construct transport')),redirect_stdout(Output()):
            self.assertEqual(cli.main(),0)
        result=json.loads((output/'result.json').read_text())
        self.assertEqual(result['status'],'completed');self.assertEqual(result['budget']['requests_reserved'],0)

    def test_committed_memory_error_retains_received_and_recovers_without_inference(self):
        server=ServerFixture(['inspect_source','compare_policies','remember_evidence'])
        self.loop.run(server,max_new_requests=2,verified_weights=IDENTITY)
        with patch.object(ResearchMemory,'_import_derived',side_effect=ResearchError('MEMORY_LIMIT','fixture temporary limit')):
            with self.assertRaises(ResearchError) as error:self.loop.run(server,max_new_requests=1,verified_weights=IDENTITY)
        self.assertEqual(error.exception.code,'MEMORY_IMPORT_PENDING')
        state=self.loop.status();self.assertEqual(state['calls'][-1]['status'],'received')
        self.assertEqual(state['status'],'needs_review');self.assertIn('MEMORY_LIMIT',state['reason'])
        self.assertEqual(len(state['study']['actions']),3)
        result=self.loop.run(max_new_requests=0)
        self.assertEqual(result['status'],'active');self.assertEqual(result['calls'][-1]['status'],'applied')
        self.assertEqual(len(result['study']['memory_context']['entries']),2)
        self.assertEqual(len(server.bodies),3)

    def test_memory_recovery_does_not_release_a_separate_financial_hold(self):
        server=ServerFixture(['inspect_source','compare_policies','remember_evidence'])
        self.loop.run(server,max_new_requests=2,verified_weights=IDENTITY);server.credit_hold='unreconciled-account'
        with patch.object(ResearchMemory,'_import_derived',side_effect=ResearchError('EVIDENCE_CONFLICT','fixture')):
            with self.assertRaises(ResearchError):self.loop.run(server,max_new_requests=1,verified_weights=IDENTITY)
        self.assertEqual(self.loop.status()['reason'],'CLOUD_CREDIT_RECONCILIATION_REQUIRED')
        result=self.loop.run(max_new_requests=0)
        self.assertEqual(result['calls'][-1]['status'],'applied')
        self.assertEqual(result['status'],'needs_review')
        self.assertEqual(result['reason'],'CLOUD_CREDIT_RECONCILIATION_REQUIRED')

    def test_postcommit_non_domain_errors_are_not_invalid_model_decisions(self):
        for index,failure in enumerate([ValueError('bad stored JSON'),KeyError('missing record field'),OSError('write failed'),RuntimeError('unexpected importer failure')]):
            loop=module.ChemoTopoCloudLoop(Path(self.directory.name)/('error-'+str(index)))
            loop.study.create('fixture-source','Postcommit error classification fixture.');loop.configure(IDENTITY,max_requests=8)
            server=ServerFixture(['inspect_source','compare_policies','remember_evidence'])
            loop.run(server,max_new_requests=2,verified_weights=IDENTITY)
            with patch.object(ResearchMemory,'_import_derived',side_effect=failure):
                with self.assertRaises(ResearchError):loop.run(server,max_new_requests=1,verified_weights=IDENTITY)
            self.assertEqual(loop.status()['calls'][-1]['status'],'received')
            restored=loop.run(max_new_requests=0)
            self.assertEqual(restored['calls'][-1]['status'],'applied')
            self.assertEqual(len(restored['study']['memory_context']['entries']),2)
            self.assertEqual(len(server.bodies),3)

    def test_process_interrupt_is_not_swallowed_and_received_is_recoverable(self):
        server=ServerFixture(['inspect_source','compare_policies','remember_evidence'])
        self.loop.run(server,max_new_requests=2,verified_weights=IDENTITY)
        with patch.object(ResearchMemory,'_import_derived',side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):self.loop.run(server,max_new_requests=1,verified_weights=IDENTITY)
        self.assertEqual(self.loop.status()['calls'][-1]['status'],'received')
        restored=self.loop.run(max_new_requests=0)
        self.assertEqual(restored['calls'][-1]['status'],'applied')


if __name__=='__main__':unittest.main()
