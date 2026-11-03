import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import nullcontext

from autoresearch import diagnostic_view as view, iterative_diagnosis_evidence as evidence
from autoresearch.contracts import ResearchError, fingerprint
from test_iterative_diagnosis import synthetic, action


class DiagnosticViewTests(unittest.TestCase):
    def test_active_snapshot_binding_native_and_assessment(self):
        source=synthetic();iteration=source['prior_source']['original_source']['iteration'];result=evidence.inspect_topography(source)
        actual=action(1,'inspect_topography',{},result);actual['id']='current-analysis'
        judgment=action(2,'investigate_data_mapping',{'finding':'all groups worse','next_check':'check'}, {'summary':{'model_assertion':{'finding':'all groups worse'}}});judgment['id']='current-judgment'
        state={'configuration_sha256':'a'*64,'status':'active','goal':'fixture','scope':source['scope'],'actions':[actual,judgment]}
        spec={'max_requests':5,'model_identity':{'model':'fixture-model'}}
        raw=[{'ordinal':1,'status':'applied','action_id':actual['id'],'response_json':json.dumps({'message':{'content':'','thinking':'secret','tool_calls':[{'function':{'name':'inspect_topography','arguments':{'reason':'model reason'}}}]}}),'error_code':None},
             {'ordinal':2,'status':'applied','action_id':judgment['id'],'response_json':json.dumps({'message':{'content':'','tool_calls':[{'function':{'name':'investigate_data_mapping','arguments':{'finding':'all groups worse'}}}]}}),'error_code':None},
             {'ordinal':3,'status':'invalid','action_id':None,'response_json':json.dumps({'message':{'content':'plain unapproved text','thinking':'secret'}}),'error_code':'MISSING_TOOL_CALL'}]
        trace=[{'ordinal':r['ordinal'],'status':r['status'],'action_id':r['action_id'],'request_sha256':'d'*64,'response_sha256':'e'*64,'feedback_action_ids':[]} for r in raw]
        class Con:
            def execute(self,*args):return raw
        study=SimpleNamespace(_connect=lambda:nullcontext(Con()),_state=lambda con:({'fixture':1},state,state['actions']),_source=lambda config:source)
        loop=SimpleNamespace(_connect=lambda:nullcontext(Con()),_state=lambda con:({'status':'active','reason':None},spec,state),study=study)
        annotation={'schema_version':'p02-diagnostic-assessment-v1','source_snapshot_sha256':source['snapshot_sha256'],'judgment_action_id':judgment['id'],'status':'needs_revision','origin':'operator_assistant_inspection','notes':['Group counts do not support the claim.']}
        with patch.object(view,'IterativeDiagnosisCloudLoop',return_value=loop),patch.object(view,'_identities',return_value={'same':'hash'}),patch.object(view,'_bind_native',return_value=({actual['id'],judgment['id']},trace)):
            result=view.capture_diagnostic('ignored',iteration,annotation)
            self.assertEqual(result['study_status'],'active');self.assertFalse(result['terminal_control_applied']);self.assertEqual(len(result['native_trace']),3)
            self.assertEqual(result['native_trace'][2]['content'],'plain unapproved text');self.assertNotIn('secret',json.dumps(result))
            self.assertEqual(result['assessment']['origin'],'operator_assistant_inspection');self.assertEqual(len(result['topography_chart']),8)
            raw[0]['status']='received'
            with self.assertRaises(ResearchError):view.capture_diagnostic('ignored',iteration)


if __name__=='__main__':unittest.main()
