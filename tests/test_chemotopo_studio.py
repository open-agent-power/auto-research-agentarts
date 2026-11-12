import copy
import http.client
import json
import sys
import threading
import types
from unittest.mock import patch

import unittest
from autoresearch import chemotopo_studio as studio
from autoresearch.contracts import canonical
from test_chemotopo_iteration_studio import fixture_view


class ConfiguredStudioTests(unittest.TestCase):
 def test_configured_route_and_baseline_identity(self):
     publication={'snapshot_sha256':'a'*64,'archive':None,'comparison':None,'prediction':None,'memory':{'entries':[]}}
     view=fixture_view(); view['protocol']={'candidates':[{'id':'a3','alpha':3},{'id':'a30','alpha':30}]}
     for row,alpha in zip(view['comparisons'],(3,30)): row['alpha']=alpha
     fake=types.ModuleType('autoresearch.configured_iteration_view')
     fake.load_configured_view=lambda workspace,base,*,native_interface='legacy':copy.deepcopy(view)
     report=types.ModuleType('autoresearch.chemotopo_iteration_report')
     report.read_iteration_artifacts=lambda directory,project:{'report.pdf':b'PDF','reproduction.zip':b'ZIP'}
     with patch.object(studio,'load_publication',return_value=publication),patch.dict(sys.modules,{'autoresearch.configured_iteration_view':fake,'autoresearch.chemotopo_iteration_report':report}):
         with self.assertRaises(ValueError): studio.create_server('fixture',0,iteration_workspace='old',configured_iteration_workspace='new')
         server=studio.create_server('fixture',0,configured_iteration_workspace='new',iteration_report_directory='reports')
     thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
     try:
         def request(path, method='GET'):
             c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5);c.request(method,path);r=c.getresponse(); result=(r.status,r.read());c.close();return result
         assert request('/api/p02/research')[1]==canonical(publication).encode()
         assert json.loads(request('/api/p02/iteration')[1])==view
         assert request('/api/p02/iteration')[1]==request('/api/p02/iteration.json')[1]
         assert request('/api/p02/iteration-report.pdf')[1]==b'PDF'
         assert request('/api/p02/iteration','POST')[0]==405
     finally:
         server.shutdown();server.server_close();thread.join()

 def test_configured_chart_zero_to_four_candidates_and_finite_values(self):
     view=fixture_view();view['protocol']={'candidates':[]};view['comparisons']=[]
     assert '仅化学' in studio.render_iteration_comparison(view).decode()
     source=fixture_view()['comparisons'][0]
     for alpha in (3,30,100,200):
         item=copy.deepcopy(source);item['alpha']=alpha;view['comparisons'].append(item)
     svg=studio.render_iteration_comparison(view).decode()
     assert all(f'α={alpha}' in svg for alpha in (3,30,100,200))
     assert 'height="1042"' in svg
     view['comparisons'][0]['policies'][0]['mae']=float('nan')
     with self.assertRaises(ValueError): studio.render_iteration_comparison(view)

