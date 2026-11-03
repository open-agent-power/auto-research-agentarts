import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from autoresearch import diagnostic_followup as followup, ollama_cloud
from autoresearch.contracts import ResearchError, canonical, fingerprint
from test_chemotopo_cloud import IDENTITY


class DiagnosticFollowupTests(unittest.TestCase):
    def test_named_tool_compact_args_replay_and_terminal_without_redo(self):
        payload={'schema_version':'p02-diagnostic-followup-source-v1','scope':{'fixture':True},
                 'summary':{'topography_available':True,'candidate_first_same_policy_chemistry_groups':{'worse_groups':21,'group_count':26},
                            'invalid_requests':[{'ordinal':2,'error_code':'INVALID_REQUEST','tool_name':'record_diagnosis'}]},
                 'prior_study':{'actions':[{'id':'prior-chem','ordinal':1,'action':'inspect_residuals','parameters':{'dimension':'chemistry'},'result_sha256':'a'*64},
                                            {'id':'prior-policy','ordinal':2,'action':'compare_policies','parameters':{},'result_sha256':'b'*64}],
                                'invalid_requests':[{'direction':'LONG_INVALID_PROSE_KEPT_ONLY_IN_SOURCE'}]}}
        payload['snapshot_sha256']=fingerprint(payload)
        prepare=Mock(return_value=copy.deepcopy(payload));topography=Mock()
        evidence=SimpleNamespace(__file__=__file__,prepare_source=prepare,validate_source=lambda value:None,
                                 decision_summary=lambda value:copy.deepcopy(value['summary']),inspect_topography=topography)
        class Server:
            def __init__(self):
                self.bodies=[];self.credit_hold=None;self.http=SimpleNamespace(request=self.call)
                self.steps=iter([('investigate_target_definition',{'finding':'Original conditional finding','next_check':'Separately verify a source mapping'}),('pause',{})])
            def assert_owner(self):pass
            def configure_budget(self,*args):pass
            def prepare(self,*args):pass
            def call(self,route,body,timeout):
                self.bodies.append(copy.deepcopy(body));name,args=next(self.steps)
                return {'model':ollama_cloud.REMOTE_MODEL,'done':True,'prompt_eval_count':100,'eval_count':50,
                        'message':{'content':'','tool_calls':[{'function':{'name':name,'arguments':{'reason':'Exact original reason',**args}}}]}}
        with tempfile.TemporaryDirectory() as temp,patch.object(followup,'evidence_module',return_value=evidence):
            loop=followup.DiagnosticFollowupCloudLoop(Path(temp)/'followup')
            loop.study.create(Path(temp)/'prior','Choose a no-refit direction',max_requests=4);loop.configure(IDENTITY)
            initial=loop.study.observe();server=Server()
            self.assertIn('investigate_target_definition',followup.available_actions(initial))
            self.assertNotIn('compare_policies',followup.available_actions(initial))
            with patch.object(loop,'_record_applied',side_effect=ResearchError('EVIDENCE_CHANGED','after commit')):
                with self.assertRaises(ResearchError):loop.run(server,max_new_requests=1,verified_weights=IDENTITY)
            self.assertEqual(len(loop.study.observe()['actions']),1)
            loop.run(max_new_requests=0)
            bad={'message':{'tool_calls':[{'function':{'name':'investigate_target_definition','arguments':{
                'reason':'Exact original reason','finding':'Original conditional finding','next_check':'Separate check','direction':'a long prose instead of an enum'}}}]}}
            with self.assertRaises(ResearchError):loop._parse_decision(bad,initial,'wrong-fields',server.bodies[0])
            tampered=copy.deepcopy(server.bodies[0]);context=json.loads(tampered['messages'][1]['content'])
            context['prior_actual_diagnostics']['candidate_first_same_policy_chemistry_groups']['worse_groups']=0
            tampered['messages'][1]['content']=canonical(context)
            with self.assertRaises(ResearchError):loop._parse_decision(bad,initial,'tampered-context',tampered)
            result=loop.run(server,max_new_requests=1,verified_weights=IDENTITY)
            self.assertEqual(result['study']['status'],'paused');self.assertEqual(result['budget']['requests_reserved'],2)
            action=result['study']['actions'][0]
            self.assertEqual(action['action'],'investigate_target_definition')
            self.assertEqual(action['parameters'],{'finding':'Original conditional finding','next_check':'Separately verify a source mapping'})
            self.assertFalse(action['result']['assertion_verified'])
            self.assertEqual({t['function']['name'] for t in server.bodies[-1]['tools']},{'pause','stop'})
            self.assertEqual({t['function']['name'] for t in followup.tools_for(initial,True)},{'pause','stop'})
            self.assertNotIn('LONG_INVALID_PROSE_KEPT_ONLY_IN_SOURCE',canonical(server.bodies))
            self.assertIn('LONG_INVALID_PROSE_KEPT_ONLY_IN_SOURCE',(loop.study.root/'source.json').read_text(encoding='utf-8'))
            self.assertEqual(prepare.call_count,1);topography.assert_not_called()
            self.assertEqual(loop.run(max_new_requests=0)['budget']['requests_reserved'],2)


if __name__=='__main__':unittest.main()
