"""Synthetic-only coverage for the Bike 2011 host driver."""
import csv
import datetime
import importlib.util
import json
from pathlib import Path
import tempfile
import io
import sys
import zipfile
import unittest
from unittest.mock import patch

from autoresearch import tabular_quality_adapter as tabular
from autoresearch.contracts import canonical

spec = importlib.util.spec_from_file_location('bike_driver', Path(__file__).resolve().parents[1]/'scripts/run_bike_2011_study.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
prep_spec = importlib.util.spec_from_file_location('bike_preparer', Path(__file__).resolve().parents[1]/'scripts/prepare_bike_2011_source.py')
prep = importlib.util.module_from_spec(prep_spec)
prep_spec.loader.exec_module(prep)

class BikeDriverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='bike-driver-synthetic-')
        root = Path(self.tmp.name)
        self.work = root/'runs'/d.STUDY
        self.claim = root/'.study-claims'/(d.STUDY+'.json')
        self.claim.parent.mkdir()
        self.identity = {'commit':'a'*40,'project_core':'synthetic','controller_core':'synthetic',
                         'driver_sha256':'1'*64,'preparation_sha256':'2'*64,'protocol_sha256':'3'*64,
                         'python':sys.version,'executable':str(Path(sys.executable).resolve()),'unicode':'synthetic','dependencies':{}}
        self.patches = [patch.object(d,'WORKSPACE',self.work),patch.object(d,'CLAIM',self.claim),
                        patch.object(d,'published_identity',return_value=self.identity),patch.object(d,'active_owner',return_value='test')]
        for p in self.patches: p.start()
        d.init()
        source_text = io.StringIO(newline='')
        writer = csv.writer(source_text,lineterminator='\n')
        writer.writerow(['dteday','workingday','temp','cnt','extra'])
        for i in range(365):
            writer.writerow([(datetime.date(2011,1,1)+datetime.timedelta(days=i)).isoformat(),str(i%2),str(i%89),str(100+i%89),'synthetic'])
        archive = Path(self.tmp.name)/'artificial.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('day.csv',source_text.getvalue())
            z.writestr('Readme.txt','Synthetic test data with no real Bike records.\n')
        root = self.work/'source'
        class FakeResponse(io.BytesIO):
            headers = {'Content-Encoding':'identity','Content-Length':str(archive.stat().st_size)}
            def geturl(self): return prep.URL
        class FakeOpener:
            def open(self, request, timeout): return FakeResponse(archive.read_bytes())
        with patch.object(prep,'_production_claim',return_value=(self.work,self.identity)), \
             patch.object(prep.urllib.request,'build_opener',return_value=FakeOpener()):
            acquired = prep.acquire()
            prep.prepare(self.work/'acquisition/original.zip',root,
                         expected_zip_sha256=acquired['sha256'],acquired_at_utc=acquired['acquired_at_utc'])
        evidence = {}
        for name, relative, url in (('uci_dataset','evidence/uci-dataset.html','https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset'),
                                    ('uci_metadata','evidence/uci-metadata.json','https://archive.ics.uci.edu/api/dataset?id=275'),
                                    ('license','evidence/cc-by-4.0.html','https://creativecommons.org/licenses/by/4.0/')):
            path=self.work/relative;path.parent.mkdir(exist_ok=True);path.write_bytes(b'synthetic evidence')
            evidence[name]={'path':relative,'url':url,'bytes':path.stat().st_size,'sha256':d.sha(path.read_bytes())}
        review={'schema_version':'bike-2011-source-review-v1','receipt_sha256':d.sha((root/'receipt.json').read_bytes()),
                'reviewer':'test','reviewed_at_utc':'synthetic','source_verified':True,'license_verified':True,'fields_verified':True,'notes':'synthetic only',
                'preparation_marker_sha256':d.sha((self.work/'source-preparation-started.json').read_bytes()), 'official_evidence':evidence}
        d.save_json(self.work/'source-review.json',review)

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def test_synthetic_lifecycle_and_closed_reissue(self):
        with d.selected_execution_guards():
            for stage in d.STAGES:
                d.run_stage(stage)
        self.assertEqual(d.last_completed(),list(d.STAGES))
        self.assertEqual(d.read_json(d.request_path('plan3','.result'))['state']['budget']['local_tool_calls_used'],2)
        with self.assertRaises(RuntimeError): d.run_stage('quality')

    def test_partial_request_and_changed_source_stop(self):
        d.run_stage('create')
        d.save_json(d.request_path('cap',''),{'original':'incomplete'})
        with self.assertRaisesRegex(RuntimeError,'Incomplete original request'): d.run_stage('cap')
        (self.work/'source/day.csv').write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'Source changed'): d.checked_source()

    def test_unknown_overrides_nonpositive_and_invalid_counts(self):
        rows=[{'workingday':str(i%2)} for i in range(365)]
        item=lambda n,r:{'predictor':'temp','n':n,'excluded':0,'pearson_r':r,'reason':None}
        res={'summary':{'rows':365,'group_count':2,'incomplete_group_rows':0},'overall':[item(365,-0.1)],
             'groups':[{'first_coordinate':{'logical_record':1},'rows':183,'associations':[item(183,0.1)]},
                       {'first_coordinate':{'logical_record':2},'rows':182,'associations':[item(182,None)]}]}
        self.assertEqual(d.association_outcome(res,rows)['outcome'],'unknown')
        res['groups'][1]['associations'][0]=item(183,0.1)
        res['groups'][1]['associations'][0]['excluded']=-1
        self.assertEqual(d.association_outcome(res,rows)['outcome'],'unknown')

if __name__ == '__main__': unittest.main()
