import hashlib
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile
from io import BytesIO

from autoresearch.c01_studio import create_server


class C01StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'input.zip'
        self.source.write_bytes(b'fixture source bytes')
        metric = {'target':'a','target_label':'cell','target_unit':'unit','n':8,'mae':2.0,'baseline_mae':1.0,'r2':-1.0,'better_than_baseline':False}
        round_ = {'id':'r1','title':'First','method':'LOO','feedback':'not improved','metrics':[metric],'limitations':'n=8','next_action':'review'}
        import autoresearch.c01 as c01
        self.summary = {'schema_version':'c01-analysis-v1','case_id':'C01-TNZST','analysis_code_sha256':hashlib.sha256(Path(c01.__file__).read_bytes()).hexdigest(),'source':{'archive_sha256':hashlib.sha256(self.source.read_bytes()).hexdigest(),'doi':'10.17632/tt7gwkpck8.1'},'data':{'sample_count':8},'rounds':[round_,{**round_,'id':'r2'}],'audit':[{'field':'labels','issue':'uncertain','handling':'review'}],'figure_status':'generated','artifacts':{'figures':[{'path':'figures/loo_mae.svg'},{'path':'figures/loo_predictions.svg'}]}}
        (self.root/'summary.json').write_text(json.dumps(self.summary),encoding='utf-8')
        for name in ['source-manifest.json','audit.csv','cleaned_samples.csv','loo_predictions.csv','rounds.csv']:
            (self.root/name).write_text('fixture',encoding='utf-8')
        (self.root/'figures').mkdir()
        (self.root/'figures'/'loo_mae.svg').write_text('<svg/>',encoding='utf-8')
        (self.root/'figures'/'loo_predictions.svg').write_text('<svg/>',encoding='utf-8')
        attachments=self.root/'evidence'/'attachments';attachments.mkdir(parents=True)
        (self.root/'evidence'/'input.zip').write_bytes(self.source.read_bytes())
        for name in ['TNZST_Summary table.xlsx','TNZST_Summary table_bio.xlsx','TNZST_SFE calculation ver 3.xlsx','TNZST_XRD.xlsx','TNZST_Eng_Stress_vs_Eng_Strain.csv']:
            (attachments/name).write_text('fixture',encoding='utf-8')
        self.manifest()

    def manifest(self):
        from autoresearch.c01_studio import _REQUIRED, _FIGURES
        names=sorted(_REQUIRED|_FIGURES)
        hashes={name:hashlib.sha256((self.root/name).read_bytes()).hexdigest() for name in names}
        (self.root/'output-manifest.json').write_text(json.dumps({'schema_version':'c01-output-manifest-v1','files':hashes}),encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def test_refuses_wrong_source(self):
        self.source.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            create_server(self.root,self.source,0)

    def test_refuses_modified_result_and_hardlink(self):
        (self.root/'loo_predictions.csv').write_text('changed',encoding='utf-8')
        with self.assertRaises(ValueError): create_server(self.root,self.source,0)
        (self.root/'loo_predictions.csv').write_text('fixture',encoding='utf-8')
        other=self.root/'sensitive.txt';other.write_text('fixture',encoding='utf-8')
        (self.root/'audit.csv').unlink()
        os.link(other,self.root/'audit.csv')
        with self.assertRaises(ValueError): create_server(self.root,self.source,0)

    def test_refuses_redirected_parent_and_ignores_extra_svg(self):
        (self.root/'figures'/'private-notes.svg').write_text('secret',encoding='utf-8')
        server=create_server(self.root,self.source,0)
        server.server_close()
        redirected=self.root/'redirected'
        try: redirected.symlink_to(self.root/'figures',target_is_directory=True)
        except OSError: return
        from autoresearch.c01_studio import _read_safe
        with self.assertRaises(ValueError): _read_safe(redirected/'loo_mae.svg')

    def test_routes_are_read_only_and_exports_belong_to_c01(self):
        (self.root/'figures'/'private-notes.svg').write_text('secret',encoding='utf-8')
        server = create_server(self.root,self.source,0)
        worker = threading.Thread(target=server.serve_forever,daemon=True); worker.start()
        def get(path, host=None):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
            conn.request('GET',path,headers={'Host':host or f'127.0.0.1:{server.server_port}'})
            resp=conn.getresponse(); content=resp.read(); status=resp.status; conn.close(); return status,content
        try:
            self.assertEqual(get('/api/c01')[0],200)
            self.assertIn(b'data-case="c01"',get('/')[1])
            self.assertTrue(get('/api/c01/report.pdf')[1].startswith(b'%PDF'))
            with zipfile.ZipFile(BytesIO(get('/api/c01/reproduction.zip')[1])) as z:
                self.assertEqual(z.read('input.zip'),self.source.read_bytes())
                self.assertEqual(json.loads(z.read('results/summary.json'))['case_id'],'C01-TNZST')
                self.assertNotIn('results/figures/private-notes.svg',z.namelist())
            self.assertEqual(get('/api/c01/figures/loo_mae.svg')[1],b'<svg/>')
            (self.root/'figures'/'loo_mae.svg').write_text('changed after startup',encoding='utf-8')
            self.assertEqual(get('/api/c01/figures/loo_mae.svg')[1],b'<svg/>')
            self.assertEqual(get('/api/export/paper.pdf')[0],404)
            self.assertEqual(get('/api/c01',host='attacker.example')[0],403)
        finally:
            server.shutdown(); server.server_close(); worker.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
