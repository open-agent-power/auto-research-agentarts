import copy
import http.client
import json
import sys
import threading
import types
import unittest
from unittest.mock import patch

from autoresearch import chemotopo_studio as studio
from autoresearch.contracts import canonical


POLICIES=('recorded_equal_batch','positive_equal_batch','recorded_equal_section','positive_equal_section')


def fixture_view():
    prior={name:{key:{'pooled_mae':value,'pooled_spearman_midrank':0.5} for key,value in [('chemistry',0.1),('additive',0.2),('interaction',0.3)]} for name in POLICIES}
    comparisons=[]
    for alpha in (10,100):
        comparisons.append({'action_id':f'action-{alpha}','alpha':alpha,'policies':[{'policy':name,'mae':0.25,'spearman':0.6,'alpha1_mae':0.3,'additive_mae':0.2,'chemistry_mae':0.1,'delta_vs_alpha1':-0.05,'delta_vs_additive':0.05,'delta_vs_chemistry':0.15} for name in POLICIES],
                            'improved_vs_alpha1':list(POLICIES),'worse_vs_alpha1':[],'improved_vs_additive':[],'improved_vs_chemistry':[]})
    return {'schema_version':'p02-iteration-view-v1','snapshot_sha256':'b'*64,'baseline_publication_sha256':'a'*64,
            'status':'stopped','prior_evidence':{'metrics':prior},'actions':[],'comparisons':comparisons}


class IterationStudioTests(unittest.TestCase):
    def test_frozen_iteration_routes_keep_baseline_json_and_reject_writes(self):
        publication={'snapshot_sha256':'a'*64,'archive':None,'comparison':None,'prediction':None,'memory':{'entries':[]}}
        view=fixture_view(); fake_view=types.ModuleType('autoresearch.chemotopo_iteration_view');fake_view.load_iteration_view=lambda workspace,base:copy.deepcopy(view)
        fake_report=types.ModuleType('autoresearch.chemotopo_iteration_report');fake_report.read_iteration_artifacts=lambda directory,project:{'report.pdf':b'%PDF-fixture','reproduction.zip':b'ZIP-fixture'}
        with patch.object(studio,'load_publication',return_value=publication),patch.dict(sys.modules,{'autoresearch.chemotopo_iteration_view':fake_view,'autoresearch.chemotopo_iteration_report':fake_report}):
            server=studio.create_server('ignored',0,iteration_workspace='fixture',iteration_report_directory='fixture')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(thread.join,3);self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def get(path,method='GET',host=None):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            connection.request(method,path,headers={'Host':host or f'127.0.0.1:{server.server_port}'})
            response=connection.getresponse();body=response.read();status=response.status;connection.close();return status,body
        self.assertEqual(get('/api/p02/research')[1],canonical(publication).encode())
        self.assertEqual(get('/api/p02/iteration')[1],get('/api/p02/iteration.json')[1])
        self.assertEqual(get('/api/p02/iteration')[1],(canonical(view)+'\n').encode())
        self.assertEqual(json.loads(get('/api/p02/iteration')[1]),view)
        self.assertEqual(get('/api/p02/iteration-report.pdf')[1],b'%PDF-fixture')
        self.assertEqual(get('/api/p02/iteration-reproduction.zip')[1],b'ZIP-fixture')
        downloads=json.loads(get('/api/p02/downloads')[1]);self.assertTrue(downloads['iteration_report_pdf']);self.assertFalse(downloads['report_pdf'])
        self.assertIn('α=100'.encode(),get('/api/p02/iteration-comparison.svg')[1])
        self.assertEqual(get('/api/p02/iteration',method='POST')[0],405)
        self.assertEqual(get('/api/p02/iteration',host='hostile.example')[0],403)
        view['status']='changed after start';self.assertEqual(json.loads(get('/api/p02/iteration')[1])['status'],'stopped')

    def test_missing_iteration_routes_and_invalid_chart(self):
        publication={'snapshot_sha256':'a'*64,'archive':None,'comparison':None,'prediction':None,'memory':{'entries':[]}}
        with patch.object(studio,'load_publication',return_value=publication):
            with self.assertRaises(ValueError):studio.create_server('ignored',0,iteration_report_directory='fixture')
            server=studio.create_server('ignored',0)
        self.addCleanup(server.server_close)
        view=fixture_view();view['comparisons'][0]['policies'][0]['mae']=float('nan')
        with self.assertRaises(ValueError):studio.render_iteration_comparison(view)
        self.assertEqual(studio.render_iteration_comparison(None),b'')


if __name__=='__main__':unittest.main()
