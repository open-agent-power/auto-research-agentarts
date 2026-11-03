import copy
from contextlib import nullcontext
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autoresearch.chemotopo_iteration_view import _bind_native
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.postrun_revision_view import capture_revision


class RevisionViewTests(unittest.TestCase):
    def test_revision_native_scope_retired_memory_and_assessment_origin(self):
        iteration={'schema_version':'p02-iteration-view-v1','scientific_validation':False}
        iteration['snapshot_sha256']=fingerprint(iteration)
        scope={'source_manifest_sha256':'a'*64,'inputs_sha256':'b'*64,'analysis_code_sha256':'c'*64,'protocol':'fixture'}
        payload={'source':{'view':iteration,'snapshot_sha256':'d'*64},'postrun':{'snapshot_sha256':'e'*64},
                 'seed_proposal':{'id':'seed','action':'propose_next','parameters':{'hypothesis':'old unreviewed'}},
                 'superseded_memory_id':'retired-decision','scope':scope}
        payload['snapshot_sha256']=fingerprint(payload)
        base={'configuration_sha256':'f'*64,'goal':'Revise once','status':'paused','source_snapshot_sha256':payload['snapshot_sha256'],
              'scope':scope,'actions':[]}
        config={'memory_workspace':'fixture-memory'}
        context=lambda state,remaining,errors:{'source_snapshot_sha256':state['source_snapshot_sha256'],'scope':state['scope'],
                                              'actions':state['actions'],'remaining':remaining,'previous_rejections':errors}
        actions=[];calls=[]
        for ordinal,tool in enumerate(('revise_proposal','invalid_revision','remember_revision','pause'),1):
            observation=copy.deepcopy({**base,'actions':actions});observation['observation_sha256']=fingerprint(observation)
            decision={'request_id':f'req-{ordinal}','action':tool,'observation_sha256':observation['observation_sha256'],
                      'reason':'Explicit tool reason','parameters':{},'source_citation_ids':['p02-revision-source'],
                      'evidence_action_ids':[actions[-1]['id']] if actions else []}
            body={'messages':[{'role':'system','content':'fixture'},{'role':'user','content':canonical(context(observation,7-ordinal,[]))}]}
            response={'message':{'thinking':'PRIVATE_THINKING_NOT_FOR_EXPORT','tool_calls':[{'function':{'name':tool,
                     'arguments':{k:v for k,v in decision.items() if k not in ('request_id','action')}}}]}}
            applied=tool!='invalid_revision';aid=None
            if applied:
                result={'assertion_verified':False} if tool=='revise_proposal' else {'decision':tool}
                action={**decision,'id':f'action-{len(actions)+1}','ordinal':len(actions)+1,'result':result,'result_sha256':fingerprint(result)}
                actions.append(action);aid=action['id']
            calls.append({'ordinal':ordinal,'status':'applied' if applied else 'invalid','action_id':aid,'request_id':decision['request_id'],
                          'observation_json':canonical(observation),'request_json':canonical(body),'request_sha256':fingerprint(body),
                          'response_json':canonical(response),'response_sha256':fingerprint(response),
                          'decision_json':canonical(decision) if applied else None,'error_code':None if applied else 'INVALID_EVIDENCE'})
        state={**base,'actions':actions};spec={'max_requests':6,'model_identity':{'model':'fixture'}}
        class Connection:
            def execute(self,sql):
                if 'calls' in sql:return calls
                return SimpleNamespace(fetchone=lambda:{'config':canonical(config)})
        study=SimpleNamespace(db=Path('fixture-study.sqlite'),_connect=lambda:nullcontext(Connection()),_source=lambda _:payload)
        def parse(response,observation,rid,body):
            function=response['message']['tool_calls'][0]['function']
            return {'request_id':rid,'action':function['name'],**function['arguments']}
        loop=SimpleNamespace(db=Path('fixture-cloud.sqlite'),study=study,_connect=lambda:nullcontext(Connection()),
                             _state=lambda _:({'status':'paused','reason':'MODEL_PAUSE'},spec,state),
                             _validate_response=lambda *a:None,_parse_decision=parse)
        memory={'scope':scope,'entries':[{'record':{'id':i,'kind':kind},'inclusion_status':status} for i,kind,status in
                [('obs1','fit_observation','active'),('obs2','fit_observation','active'),
                 ('new-decision','agent_decision','active'),('retired-decision','agent_decision','retired')]]}
        note={'schema_version':'postrun-assessment-v1','source_snapshot_sha256':payload['snapshot_sha256'],
              'proposal_action_id':'action-1','status':'needs_revision','origin':'operator_assistant_inspection','notes':['Unreviewed proposal.']}
        with patch('autoresearch.postrun_revision_view.RevisionCloudLoop',return_value=loop), \
             patch('autoresearch.postrun_revision_view._identities',return_value={'frozen':'hash'}), \
             patch('autoresearch.postrun_revision_view.project_context',context), \
             patch('autoresearch.postrun_revision_view.ResearchMemory') as store, \
             patch('autoresearch.postrun_revision_view._bind_native',wraps=_bind_native) as binding:
            store.return_value.recall.return_value=memory
            view=capture_revision('fixture',iteration,note)
            self.assertEqual(binding.call_args.kwargs['scope_fields'],('source_snapshot_sha256','scope'))
            store.return_value.recall.assert_called_once_with(scope,limit=8,include_retired=True)
        self.assertEqual(view['iteration_snapshot_sha256'],iteration['snapshot_sha256'])
        self.assertEqual(view['revision']['proposal_version_count'],2)
        self.assertEqual(view['revision']['superseded_memory_id'],'retired-decision')
        self.assertEqual(len(view['memory_context']['entries']),4)
        self.assertEqual(view['execution']['requests_reserved'],4)
        self.assertEqual(view['execution']['explicit_remembers'],1)
        self.assertEqual(view['execution']['explicit_recalls'],0)
        self.assertEqual(view['execution']['recalled_entries_in_later_request'],0)
        self.assertTrue(view['execution']['native_terminal_control_applied'])
        self.assertEqual(view['assessment']['origin'],'operator_assistant_inspection')
        self.assertNotIn('PRIVATE_THINKING_NOT_FOR_EXPORT',canonical(view))
        changed=copy.deepcopy(calls);observation=json.loads(changed[0]['observation_json']);observation['scope']={'changed':True}
        observation.pop('observation_sha256');observation['observation_sha256']=fingerprint(observation)
        changed[0]['observation_json']=canonical(observation)
        with self.assertRaises(ResearchError):_bind_native(loop,state,spec,changed,context_builder=context,scope_fields=('source_snapshot_sha256','scope'))


if __name__=='__main__':unittest.main()
