import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from autoresearch import diagnostic_research as diagnostic, ollama_cloud
from autoresearch.contracts import ResearchError, canonical, fingerprint
from test_chemotopo_cloud import IDENTITY


class DiagnosticResearchTests(unittest.TestCase):
    def test_native_replay_context_and_record_terminal_boundaries(self):
        payload={'schema_version':'p02-diagnostic-source-v1','scope':{'fixture':True},
                 'summary':{'alpha':.5,'new_fits':0},'inputs':{'private_full_inputs':'NO_FULL_INPUTS_IN_PROMPT'}}
        payload['snapshot_sha256']=fingerprint(payload)
        residual=Mock(side_effect=lambda source,dimension:{'summary':{'dimension':dimension,'n':8,'scientific_validation':False},
                                                         'rows':[{'marker':'NO_FULL_RESULTS_IN_PROMPT'}]})
        comparison=Mock(return_value={'summary':{'contrasts':[{'paired_n':8}],'new_fits':0},'rows':[{'marker':'NO_FULL_RESULTS_IN_PROMPT'}]})
        evidence=SimpleNamespace(__file__=__file__,prepare_source=lambda *args:copy.deepcopy(payload),
                                 validate_source=lambda value:None,inspect_residuals=residual,compare_policies=comparison)
        class Server:
            def __init__(self):
                self.bodies=[];self.credit_hold=None;self.steps=iter([
                    ('inspect_residuals',{'dimension':'topography'}),('compare_policies',{}),
                    ('record_diagnosis',{'direction':'feature_representation','finding':'Synthetic conditional finding','next_check':'A separately authorized check'}),('pause',{})])
                self.http=SimpleNamespace(request=self.call)
            def assert_owner(self):pass
            def configure_budget(self,*args):pass
            def prepare(self,*args):pass
            def call(self,route,body,timeout):
                self.bodies.append(copy.deepcopy(body));name,args=next(self.steps)
                return {'model':ollama_cloud.REMOTE_MODEL,'done':True,'prompt_eval_count':100,'eval_count':50,
                        'message':{'content':'','tool_calls':[{'type':'function','function':{'name':name,'arguments':{'reason':'Synthetic explicit reason',**args}}}]}}
        with tempfile.TemporaryDirectory() as temp,patch.object(diagnostic,'evidence_module',return_value=evidence):
            loop=diagnostic.DiagnosticCloudLoop(Path(temp)/'study');loop.study.create(Path(temp)/'source',Path(temp)/'publication','No refits',max_requests=6)
            loop.configure(IDENTITY);initial=loop.study.observe();server=Server()
            with patch.object(loop,'_record_applied',side_effect=ResearchError('EVIDENCE_CHANGED','after tool commit')):
                with self.assertRaises(ResearchError):loop.run(server,max_new_requests=1,verified_weights=IDENTITY)
            self.assertEqual(len(loop.study.observe()['actions']),1);self.assertEqual(residual.call_count,1)
            recovered=loop.run(max_new_requests=0)
            self.assertEqual(recovered['calls'][0]['status'],'applied');self.assertEqual(residual.call_count,1)
            body=server.bodies[0];tampered=copy.deepcopy(body);context=json.loads(tampered['messages'][1]['content'])
            context['source_summary']['alpha']=999;tampered['messages'][1]['content']=canonical(context)
            response={'message':{'tool_calls':[{'function':{'name':'inspect_residuals','arguments':{'dimension':'topography','reason':'Synthetic'}}}]}}
            with self.assertRaises(ResearchError):loop._parse_decision(response,initial,'tampered-request',tampered)
            state=loop.study.observe();self.assertEqual(diagnostic.tools_for(state,True)[0]['function']['name'],'pause')
            result=loop.run(server,max_new_requests=3,verified_weights=IDENTITY)
            self.assertEqual(result['study']['status'],'paused');self.assertEqual(result['budget']['requests_reserved'],4)
            self.assertEqual([a['action'] for a in result['study']['actions']],['inspect_residuals','compare_policies','record_diagnosis','pause'])
            self.assertEqual(residual.call_count,1);self.assertEqual(comparison.call_count,1)
            self.assertFalse(result['study']['actions'][2]['result']['assertion_verified'])
            for request in server.bodies:
                self.assertNotIn('NO_FULL_INPUTS_IN_PROMPT',canonical(request));self.assertNotIn('NO_FULL_RESULTS_IN_PROMPT',canonical(request))
            self.assertEqual({t['function']['name'] for t in server.bodies[-1]['tools']},{'pause','stop'})
            self.assertEqual(diagnostic.host_binding(result['study'])['origin'],'host_bound_execution_metadata')
            self.assertEqual(loop.run(max_new_requests=0)['budget']['requests_reserved'],4)


if __name__=='__main__':unittest.main()
