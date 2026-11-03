from contextlib import closing
import hashlib
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

from autoresearch.chemotopo_cloud import ChemoTopoCloudLoop
from autoresearch.chemotopo_delivery import load_delivery
from autoresearch import chemotopo_delivery as delivery
from autoresearch.chemotopo_study import ChemoTopoMemory
from autoresearch.chemotopo_studio import create_server, render_comparison
from autoresearch.contracts import ResearchError, fingerprint
from test_chemotopo_cloud import IDENTITY, ServerFixture
from test_chemotopo_study import fixture_environment, request


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        environment=fixture_environment(); environment.__enter__(); self.addCleanup(environment.__exit__,None,None,None)
        self.root=Path(directory.name)/'study'; self.loop=ChemoTopoCloudLoop(self.root)
        self.loop.study.create('fixture-source','Conditional research fixture')
        self.loop.configure(IDENTITY,max_requests=8)
        self.loop.run(ServerFixture(['inspect_source','compare_policies','remember_evidence']),max_new_requests=3,verified_weights=IDENTITY)

    def test_real_native_binding_memory_and_snapshot_fingerprint(self):
        snapshot=load_delivery(self.root)
        self.assertEqual(snapshot['schema_version'],'p02-workbench-v1')
        self.assertEqual(snapshot['case_id'],'P02-ChemoTopoChip')
        self.assertEqual(snapshot['snapshot_sha256'],fingerprint({k:v for k,v in snapshot.items() if k!='snapshot_sha256'}))
        self.assertEqual([a['action'] for a in snapshot['actions']],['inspect_source','compare_policies','remember_evidence'])
        self.assertTrue(all(a['model_selected'] for a in snapshot['actions']))
        self.assertEqual(snapshot['execution']['applied_calls'],3)
        self.assertEqual(len(snapshot['memory']['entries']),2)
        for entry in snapshot['memory']['entries']:
            self.assertEqual(fingerprint(entry['record']),entry['record_sha256'])
            self.assertTrue(entry['record']['provenance']['references'])
        raw=json.dumps(snapshot)
        self.assertNotIn(str(self.root),raw)
        self.assertNotIn('account_identity',raw)
        self.assertNotIn('tool_calls',raw)

    def test_nonmodel_action_is_not_claimed_as_model_selected(self):
        self.loop.study.apply(request(self.loop.study,'check_training_gate','manual'))
        snapshot=load_delivery(self.root)
        self.assertFalse(snapshot['actions'][-1]['model_selected'])
        self.assertTrue(snapshot['actions'][0]['model_selected'])

    def test_tampered_response_or_action_binding_is_rejected(self):
        with closing(sqlite3.connect(self.loop.db)) as con:
            con.execute("UPDATE calls SET response_json='{}' WHERE ordinal=1")
            con.commit()
        with self.assertRaises(ResearchError): load_delivery(self.root)

    def test_read_does_not_change_or_create_journals(self):
        def inventory():
            return {str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        before=inventory(); load_delivery(self.root); self.assertEqual(inventory(),before)
        missing=self.root.parent/'missing'
        with self.assertRaises(ResearchError): load_delivery(missing)
        self.assertFalse(missing.exists())

    def test_http_snapshot_download_host_and_writes(self):
        server=create_server(self.root,0); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        self.addCleanup(thread.join,3); self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        def get(path,method='GET',host=None):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            conn.request(method,path,headers={'Host':host or f'127.0.0.1:{server.server_port}'})
            response=conn.getresponse(); data=response.read(); headers=dict(response.getheaders()); status=response.status; conn.close()
            return status,data,headers
        status,raw,headers=get('/api/p02/research'); self.assertEqual(status,200)
        self.assertEqual(get('/api/p02/research.json')[1],raw)
        self.assertEqual(json.loads(get('/api/p02/memory.json')[1]),json.loads(raw)['memory'])
        self.assertIn(b'data-case="p02"',get('/')[1])
        self.assertIn('尚未确认 ALP'.encode('utf-8'),get('/api/p02/policy-comparison.svg')[1])
        self.assertEqual(get('/api/p02/research',host='evil.example')[0],403)
        self.assertEqual(get('/api/p02/research',method='POST')[0],405)
        self.assertEqual(get('/arbitrary')[0],404)
        self.assertIn('Content-Security-Policy',headers)

    def test_memory_projection_fails_closed_on_redaction_or_snapshot_change(self):
        original_safe=delivery._safe
        def redact_record(value):
            if isinstance(value,dict) and value.get('schema_version')=='conditional-research-memory-v1':
                return {**value, 'redacted': True}
            return original_safe(value)
        with patch.object(delivery, '_safe', side_effect=redact_record):
            with self.assertRaises(ResearchError) as error: load_delivery(self.root)
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')
        original_verify=ChemoTopoMemory._verify
        import inspect
        def changed_record(con,row):
            record=original_verify(con,row)
            if any(frame.function=='load_delivery' for frame in inspect.stack()):
                record={**record,'id':'different-active-id'}
            return record
        with patch.object(ChemoTopoMemory,'_verify',side_effect=changed_record):
            with self.assertRaises(ResearchError) as error: load_delivery(self.root)
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')

    def test_body_context_must_match_observation_even_with_updated_hash(self):
        with closing(sqlite3.connect(self.loop.db)) as con:
            raw=con.execute('SELECT request_json FROM calls WHERE ordinal=1').fetchone()[0]
            body=json.loads(raw); context=json.loads(body['messages'][1]['content'])
            context['memory_context']['entries']=[{'id':'forged'}]
            body['messages'][1]['content']=json.dumps(context)
            con.execute('UPDATE calls SET request_json=?,request_sha256=? WHERE ordinal=1',
                        (json.dumps(body),fingerprint(body))); con.commit()
        with self.assertRaises(ResearchError) as error: load_delivery(self.root)
        self.assertEqual(error.exception.code,'EVIDENCE_CHANGED')

    def test_manual_recall_is_not_counted_as_model_recall(self):
        self.loop.study.apply(request(self.loop.study,'recall_evidence','manual-recall'))
        snapshot=load_delivery(self.root)
        self.assertFalse(snapshot['actions'][-1]['model_selected'])
        self.assertEqual(snapshot['execution']['explicit_recalls'],0)

    def test_svg_rejects_nonfinite_values(self):
        comparison={'comparison':{'pairs':[{'left':'a','right':'b','spearman_midrank':float('nan')}]}}
        with self.assertRaises(ValueError): render_comparison(comparison)


if __name__=='__main__': unittest.main()
