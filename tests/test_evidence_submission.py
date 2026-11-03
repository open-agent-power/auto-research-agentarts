import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autoresearch import evidence_submission as submission
from autoresearch.contracts import ResearchError, canonical, fingerprint


class SubmissionTests(unittest.TestCase):
    def test_roundtrip_wrong_task_traversal_and_changed_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);incoming=root/'incoming';incoming.mkdir();(incoming/'documents').mkdir();raw=b'number,value\n1,2\n';(incoming/'documents'/'data.csv').write_bytes(raw)
            diagnostic={'iteration_snapshot_sha256':'a'*64,'snapshot_sha256':'b'*64}
            diagdir=root/'diagnostic';diagdir.mkdir();(diagdir/'diagnostic.json').write_text(canonical(diagnostic),encoding='utf8')
            handoff={'schema_version':'p02-handoff-view-v1','selected_task':{'id':'export_mapping'},'selected_action_id':'action-1','waiting_for_external_input':True,'external_task_executed':False,'scientific_validation':False,'diagnostic_snapshot_sha256':'b'*64};handoff['snapshot_sha256']=fingerprint(handoff)
            doc={'schema_version':'p02-evidence-submission-v1','handoff_snapshot_sha256':handoff['snapshot_sha256'],'selected_action_id':'action-1','task_id':'export_mapping','contributor':{'role':'teammate','label':'Reviewer'},'summary':'Preserved source evidence.','sources':[{'id':'source1','path':'documents/data.csv','sha256':hashlib.sha256(raw).hexdigest(),'url':'https://example.org/data.csv','media_type':'text/csv','license_note':'Declared by submitter.'}],'findings':[{'id':'finding1','claim':'Observed a value.','status':'observed','source_id':'source1','locator':{'kind':'json_pointer','value':'/table/rows/0'},'note':'Coordinate supplied.'}],'unresolved_questions':['Verify provenance.']}
            def write(d):(incoming/'submission.json').write_text(canonical(d),encoding='utf8')
            with patch.object(submission,'read_diagnostic_artifacts',return_value={}),patch.object(submission,'read_handoff_artifacts',return_value={'handoff.json':canonical(handoff).encode()}):
                wrong=copy.deepcopy(doc);wrong['task_id']='other';write(wrong)
                with self.assertRaises(ResearchError):submission.create_submission(root/'handoff',diagdir,incoming,root/'wrong')
                traversal=copy.deepcopy(doc);traversal['sources'][0]['path']='../data.csv';write(traversal)
                with self.assertRaises(ValueError):submission.create_submission(root/'handoff',diagdir,incoming,root/'traversal')
                write(doc);result=submission.create_submission(root/'handoff',diagdir,incoming,root/'output')
                self.assertEqual(submission.read_submission(root/'output',handoff),result)
                self.assertEqual(result['findings'][0]['locator_validation'],'provided_not_verified');self.assertEqual(result['findings'][0]['locator']['value'],'/table/rows/0')
                self.assertFalse(result['scientific_validation']);self.assertFalse(result['biological_endpoint_eligible'])
                receipt_path=root/'output'/'receipt.json';manifest_path=root/'output'/'manifest.json'
                receipt_original=receipt_path.read_bytes();manifest_original=manifest_path.read_bytes()
                forged=json.loads(receipt_original);forged['findings'][0]['source_id']='unknown'
                forged['snapshot_sha256']=fingerprint({k:v for k,v in forged.items() if k!='snapshot_sha256'})
                forged_raw=(canonical(forged)+'\n').encode('utf8');receipt_path.write_bytes(forged_raw)
                manifest=json.loads(manifest_original);manifest['receipt_sha256']=hashlib.sha256(forged_raw).hexdigest();manifest['receipt_bytes']=len(forged_raw)
                manifest['manifest_sha256']=fingerprint({k:v for k,v in manifest.items() if k!='manifest_sha256'});manifest_path.write_text(canonical(manifest)+'\n',encoding='utf8')
                with self.assertRaises(ResearchError):submission.read_submission(root/'output',handoff)
                receipt_path.write_bytes(receipt_original);manifest_path.write_bytes(manifest_original)
                (root/'output'/'sources'/'source1'/'data.csv').write_bytes(b'changed')
                with self.assertRaises(ValueError):submission.read_submission(root/'output',handoff)


if __name__=='__main__':unittest.main()
