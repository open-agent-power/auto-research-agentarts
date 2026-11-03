import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

from autoresearch import snapshot_viewer as viewer


def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def build(root):
    root=Path(root);memory={'entries':[],'scope':{}}
    base={'schema_version':'p02-workbench-v1','case_id':'P02-ChemoTopoChip','scientific_validation':False,'memory':memory,'archive':None,'prediction':{'metrics':{}},'comparison':None}
    base['snapshot_sha256']=viewer._fingerprint(base)
    iteration={'schema_version':'p02-iteration-view-v1','scientific_validation':False,'baseline_publication_sha256':base['snapshot_sha256']}
    iteration['snapshot_sha256']=viewer._fingerprint(iteration)
    files={'serve.py':Path(viewer.__file__).read_bytes(),'README.md':b'readme','AGENT-START.md':b'agent',
           'web/index.html':b'<html><body></body></html>','web/app.js':b'js','web/app.css':b'css','web/vendor-licenses.txt':b'licenses',
           'data/research.json':encoded(base),'data/memory.json':encoded(memory),'data/iteration.json':encoded(iteration),
           'figures/prediction.svg':b'<svg/>','figures/iteration-comparison.svg':b'<svg/>',
           'reports/baseline-report.pdf':b'%PDF-base','reports/baseline-reproduction.zip':b'zip',
           'reports/iteration-report.pdf':b'%PDF-iter','reports/iteration-reproduction.zip':b'zip2'}
    manifest={'schema_version':'p02-handoff-bundle-v1','baseline_snapshot_sha256':base['snapshot_sha256'],
              'iteration_snapshot_sha256':iteration['snapshot_sha256'],'files':{}}
    for name,raw in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        manifest['files'][name]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    (root/'bundle-manifest.json').write_bytes(encoded(manifest))
    return base,iteration,manifest


class SnapshotViewerTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name);self.base,self.iteration,self.manifest=build(self.root)

    def test_postrun_optional_exact_routes_and_rehashed_wrong_binding_rejected(self):
        def serve():
            server=viewer.create_server(self.root,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            self.addCleanup(thread.join,3);self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
            return server
        def get(server,path):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            connection.request('GET',path);response=connection.getresponse();value=(response.status,response.read());connection.close();return value
        legacy=serve();self.assertEqual(get(legacy,'/api/p02/postrun')[0],404)
        original_pdf=(self.root/'reports/iteration-report.pdf').read_bytes()
        post={'schema_version':'p02-postrun-view-v1','iteration_snapshot_sha256':self.iteration['snapshot_sha256'],
              'source_snapshot_sha256':'b'*64,'scientific_validation':False}
        def save():
            post['snapshot_sha256']=viewer._fingerprint({k:v for k,v in post.items() if k!='snapshot_sha256'})
            raw=encoded(post);(self.root/'data/postrun.json').write_bytes(raw)
            self.manifest['postrun_snapshot_sha256']=post['snapshot_sha256']
            self.manifest['files']['data/postrun.json']={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
            (self.root/'bundle-manifest.json').write_bytes(encoded(self.manifest));return raw
        raw=save();self.assertEqual(viewer.load_bundle(self.root)['data/postrun.json'],raw)
        current=serve();self.assertEqual(get(current,'/api/p02/postrun'),(200,raw))
        self.assertEqual(get(current,'/api/p02/postrun.json'),(200,raw))
        self.assertEqual(get(current,'/api/p02/iteration-report.pdf')[1],original_pdf)
        self.assertEqual(get(legacy,'/api/p02/postrun')[0],404)
        post['iteration_snapshot_sha256']='c'*64;save()
        with self.assertRaises(ValueError):viewer.load_bundle(self.root)

    def test_postrun_history_requires_exact_known_snapshot_and_preserves_its_source(self):
        history_sha='a'*64
        self.iteration['prior_evidence']={'known_iterations':[{'snapshot_sha256':history_sha}]}
        self.iteration['snapshot_sha256']=viewer._fingerprint({k:v for k,v in self.iteration.items() if k!='snapshot_sha256'})
        self.manifest['iteration_snapshot_sha256']=self.iteration['snapshot_sha256']
        def file(name,value):
            raw=encoded(value);(self.root/name).write_bytes(raw)
            self.manifest['files'][name]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
            return raw
        file('data/iteration.json',self.iteration)
        post={'schema_version':'p02-postrun-view-v1','iteration_snapshot_sha256':history_sha,'scientific_validation':False}
        def save():
            post['snapshot_sha256']=viewer._fingerprint({k:v for k,v in post.items() if k!='snapshot_sha256'})
            raw=file('data/postrun.json',post);self.manifest['postrun_snapshot_sha256']=post['snapshot_sha256']
            (self.root/'bundle-manifest.json').write_bytes(encoded(self.manifest));return raw
        raw=save();self.assertEqual(viewer.load_bundle(self.root)['data/postrun.json'],raw)
        self.assertEqual(json.loads(raw)['iteration_snapshot_sha256'],history_sha)
        post['iteration_snapshot_sha256']='b'*64;save()
        with self.assertRaises(ValueError):viewer.load_bundle(self.root)

    def test_changed_bytes_and_mismatched_binding_are_rejected(self):
        (self.root/'web/app.js').write_bytes(b'changed')
        with self.assertRaises(ValueError):viewer.load_bundle(self.root)
        build(self.root)
        self.iteration['baseline_publication_sha256']='a'*64
        self.iteration['snapshot_sha256']=viewer._fingerprint({k:v for k,v in self.iteration.items() if k!='snapshot_sha256'})
        raw=encoded(self.iteration);(self.root/'data/iteration.json').write_bytes(raw)
        self.manifest['iteration_snapshot_sha256']=self.iteration['snapshot_sha256']
        self.manifest['files']['data/iteration.json']={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
        (self.root/'bundle-manifest.json').write_bytes(encoded(self.manifest))
        with self.assertRaises(ValueError):viewer.load_bundle(self.root)

    def test_frozen_exact_routes_host_and_readonly(self):
        server=viewer.create_server(self.root,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(thread.join,3);self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def get(path,method='GET',host=None):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            c.request(method,path,headers={'Host':host or f'127.0.0.1:{server.server_port}'})
            r=c.getresponse();status=r.status;raw=r.read();c.close();return status,raw
        research=get('/api/p02/research')[1]
        self.assertEqual(research,(self.root/'data/research.json').read_bytes())
        self.assertEqual(research,get('/api/p02/research.json')[1])
        self.assertEqual(get('/api/p02/iteration')[1],get('/api/p02/iteration.json')[1])
        self.assertIn(b'data-case="p02"',get('/')[1])
        self.assertEqual(get('/api/p02/iteration-report.pdf')[1],b'%PDF-iter')
        self.assertEqual(get('/api/p02/archive.json')[0],404)
        self.assertEqual(get('/../data/research.json')[0],404)
        self.assertEqual(get('/api/p02/research',method='POST')[0],405)
        self.assertEqual(get('/api/p02/research',host='evil.example')[0],403)
        (self.root/'data/research.json').write_bytes(b'changed after startup')
        self.assertEqual(get('/api/p02/research')[1],research)

    def test_extra_missing_and_redirected_paths_rejected(self):
        if os.name=='nt':
            Path(str(self.root/'web/app.js')+':Zone.Identifier').write_text('[ZoneTransfer]\nZoneId=3\n',encoding='utf-8')
            self.assertIn('web/app.js',viewer.load_bundle(self.root))
            other=str(self.root/'web/app.css')+':unexpected'
            Path(other).write_text('not allowed',encoding='utf-8')
            with self.assertRaises(ValueError):viewer.load_bundle(self.root)
            os.remove(other)
        (self.root/'extra.txt').write_text('extra')
        with self.assertRaises(ValueError):viewer.load_bundle(self.root)
        (self.root/'extra.txt').unlink();(self.root/'data/memory.json').unlink()
        with self.assertRaises(ValueError):viewer.load_bundle(self.root)
        build(self.root)
        self.manifest['files']['data/evil:stream']={'sha256':'0'*64,'bytes':0}
        (self.root/'bundle-manifest.json').write_bytes(encoded(self.manifest))
        with self.assertRaises(ValueError):viewer.load_bundle(self.root)


if __name__=='__main__':unittest.main()
