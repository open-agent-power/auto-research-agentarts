import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autoresearch import returned_evidence as evidence
from autoresearch.contracts import ResearchError, canonical


class ReturnedEvidenceTests(unittest.TestCase):
    def test_selected_pdf_json_locators_bad_pointer_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'diag').mkdir();(root/'diag'/'diagnostic.json').write_text(canonical({'iteration_snapshot_sha256':'a'*64}),encoding='utf8')
            source=root/'submission'/'sources';(source/'pdf').mkdir(parents=True);(source/'json').mkdir()
            pdf=b'%PDF-fixture';document=b'{"a/b":{"value":"Evidence from JSON"}}';(source/'pdf'/'file.pdf').write_bytes(pdf);(source/'json'/'file.json').write_bytes(document)
            records=[{'id':'pdf','path':'sources/pdf/file.pdf','sha256':hashlib.sha256(pdf).hexdigest(),'url':'https://example.org/file.pdf','media_type':'application/pdf','license_note':'fixture','bytes':len(pdf)},
                     {'id':'json','path':'sources/json/file.json','sha256':hashlib.sha256(document).hexdigest(),'url':'https://example.org/file.json','media_type':'application/json','license_note':'fixture','bytes':len(document)}]
            def finding(id,source,kind,value):return {'id':id,'claim':'pending assertion','status':'observed','source_id':source,'locator':{'kind':kind,'value':value},'note':'fixture','locator_validation':'provided_not_verified'}
            receipt={'snapshot_sha256':'b'*64,'task_id':'export_mapping','contributor':{'role':'teammate','label':'fixture'},'sources':records,'findings':[finding('f1','pdf','pdf_page','3,4'),finding('f2','json','json_pointer','/a~1b/value'),finding('f3','json','xlsx_cell','A1')],'unresolved_questions':[]}
            pages=['unused','unused','A'*4501,'page four'];handoff={'snapshot_sha256':'c'*64}
            with patch.object(evidence,'read_diagnostic_artifacts',return_value={}),patch.object(evidence,'read_handoff_artifacts',return_value={'handoff.json':canonical(handoff).encode()}),patch.object(evidence.evidence_submission,'read_submission',return_value=receipt),patch.object(evidence.guard,'_extract_pdf',return_value=(pages,2)):
                packet=evidence.build_returned_evidence(root/'handoff',root/'diag',root/'submission');evidence.validate_packet(packet)
                self.assertEqual(len(packet['chunks']),4);self.assertEqual([c['locator']['value'] for c in packet['chunks']],['3','3','4','/a~1b/value'])
                self.assertEqual([(c['start_char'],c['end_char']) for c in packet['chunks'][:2]],[(0,4000),(4000,4501)])
                self.assertEqual(packet['extractor']['warning_count'],2);self.assertEqual(packet['exclusions'][0]['reason'],'unsupported_locator_type')
                self.assertEqual(evidence.read_chunks(packet,[packet['chunks'][-1]['id']])[0]['text'],'Evidence from JSON')
                receipt['findings'][1]['locator']['value']='/does-not-exist'
                with self.assertRaises(ResearchError):evidence.build_returned_evidence(root/'handoff',root/'diag',root/'submission')
                receipt['findings'][1]['locator']['value']='/a~1b/value';(source/'json'/'file.json').write_bytes(b'changed')
                with self.assertRaises(ValueError):evidence.build_returned_evidence(root/'handoff',root/'diag',root/'submission')


if __name__=='__main__':unittest.main()
