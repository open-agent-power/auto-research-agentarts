"""Memory protocol tests with synthetic data/transport, never real model evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from autoresearch.c01_cloud_loop import C01CloudLoop
from autoresearch.c01_cloud_memory import C01CloudMemoryLoop, candidate_comparison, compact_provenance
from autoresearch.c01_memory_context import MemoryContext
from autoresearch.c01_research import C01Research
from autoresearch.c01_research_outputs import public_record
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.research_memory import ResearchMemory
import test_c01_research as fixture
from test_c01_cloud_loop import FakeCloud, IDENTITY
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_cloud_research as cli


class CloudMemoryTests(unittest.TestCase):
    def setUp(self):
        self.base=fixture.C01ResearchTests('test_terminal_decision_is_durable_and_stops_new_dispatch')
        self.base.setUp();self.addCleanup(self.base.doCleanups)
        self.base.search()
        for alpha in (1,10):
            self.base.study.apply(self.base.request('fit',{'alpha':alpha,'features':self.base.study.observe()['data']['features'],
                'hypothesis':'UNREVIEWED_HYPOTHESIS_DO_NOT_INJECT','expected_effect':'UNREVIEWED_EXPECTATION_DO_NOT_INJECT'},
                reason='UNREVIEWED_FIT_REASON_DO_NOT_INJECT'))
        fit=self.base.study.observe()['actions'][-1]
        self.base.study.apply(self.base.request('residuals',{'fit_action_id':fit['id']}))
        self.base.study.apply(self.base.request('correlation'))
        self.base.study.apply(self.base.request('pause',reason='UNAPPROVED_STOP_DO_NOT_INJECT'))
        exported=self.base.study.export()
        self.memory=ResearchMemory(self.base.root/'memory')
        self.memory.import_study(public_record(exported['state']),exported['reproduction'])
        self.study=C01Research(self.base.root/'next-study')
        with patch('autoresearch.c01_research.c01.load_archive',return_value=self.base.inputs):
            self.study.create('fixture-only',self.base.index,'Synthetic cloud memory protocol test',max_fits=3)
        self.apply('search',{'query':'C01 alloy','kinds':['reuse_note']})
        self.loop=C01CloudMemoryLoop(self.study.root,memory_workspace=self.memory.root)
        self.fit_id=next(e['record']['id'] for e in MemoryContext(self.memory.root).snapshot(self.study)['entries']
                         if e['record']['kind']=='fit_observation')

    def apply(self,action,parameters=None):
        state=self.study.observe();latest=next((a['id'] for a in reversed(state['actions']) if a['action'] in {'fit','residuals','correlation'}),None)
        return self.study.apply({'request_id':'operator-'+str(len(state['actions'])),'observation_sha256':state['observation_sha256'],
            'action':action,'reason':'Synthetic operator preparation, not model research.',
            'source_citation_ids':[state['citations'][0]['citation_id']] if state['citations'] else [],
            'evidence_action_ids':[] if latest is None else [latest],'parameters':parameters or {}})

    def configure(self):return self.loop.configure(copy.deepcopy(IDENTITY),max_requests=8)

    def retire(self):self.memory.set_status(self.fit_id,'retired','Synthetic qualification withdrawal.','retire-test')

    def error(self,code,fn):
        with self.assertRaises(ResearchError) as e:fn()
        self.assertEqual(e.exception.code,code)

    def test_full_snapshot_and_actual_projection_commit_with_reservation_before_transport(self):
        self.configure()
        def before(body):
            with self.loop._connect() as con:
                row=con.execute('SELECT * FROM calls').fetchone();snapshot,sent=self.loop._use(con,row['id'])
                self.assertEqual(row['status'],'sending');self.assertEqual(json.loads(row['request_json']),body)
            context=json.loads(body['messages'][1]['content'])['research_context']
            self.assertEqual(context['conditional_memory'],sent)
            self.assertEqual(context['candidate_comparison'],candidate_comparison(self.study.observe(),sent))
            self.assertEqual(len(snapshot['entries']),4);self.assertEqual(len(sent['entries']),4)
            self.assertTrue(all(e['kind'] in {'fit_observation','diagnostic_observation'} for e in sent['entries']))
            for text in ('UNAPPROVED_STOP_DO_NOT_INJECT','UNREVIEWED_HYPOTHESIS_DO_NOT_INJECT',
                         'UNREVIEWED_EXPECTATION_DO_NOT_INJECT','UNREVIEWED_FIT_REASON_DO_NOT_INJECT',str(self.memory.root)):
                self.assertNotIn(text,canonical(body))
            self.assertLessEqual(len(canonical(body).encode('utf-8')),65536)
        server=FakeCloud(before=before);end=self.loop.run(server,max_new_requests=1)
        self.assertEqual(end['budget']['requests_reserved'],1);self.assertEqual(len(server.requests),1)
        self.assertEqual(len(end['memory']['uses']),1);self.assertEqual(end['study']['budget']['fits_used'],1)
        self.assertFalse(end['scientific_validation'])

    def test_changed_memory_before_reservation_rolls_back_both_call_and_receipt(self):
        self.configure();server=FakeCloud();server.prepare=lambda body:self.retire()
        self.error('MEMORY_CONTEXT_CHANGED',lambda:self.loop.run(server,max_new_requests=1))
        with self.loop._connect() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM calls').fetchone()[0],0)
            self.assertEqual(con.execute('SELECT count(*) FROM cloud_memory_uses').fetchone()[0],0)
        self.assertEqual(server.requests,[]);self.assertEqual(self.study.observe()['budget']['fits_used'],0)

    def test_withdrawal_after_received_rejects_uncommitted_response_and_next_request_refreshes(self):
        self.configure();server=FakeCloud()
        with patch.object(self.loop,'_consume',side_effect=RuntimeError('synthetic after receive')):
            with self.assertRaises(RuntimeError):self.loop.run(server,max_new_requests=1)
        original=copy.deepcopy(server.requests[0]);self.retire()
        resumed=C01CloudMemoryLoop(self.study.root)
        end=resumed.run(max_new_requests=0)
        self.assertEqual(end['calls'][0]['error_code'],'MEMORY_CONTEXT_CHANGED')
        self.assertEqual(end['budget']['requests_reserved'],1);self.assertEqual(end['study']['budget']['fits_used'],0)
        next_server=FakeCloud();end=resumed.run(next_server,max_new_requests=1)
        self.assertEqual(end['budget']['requests_reserved'],2)
        old_ctx=json.loads(original['messages'][1]['content'])['research_context']['conditional_memory']
        new_ctx=json.loads(next_server.requests[0]['messages'][1]['content'])['research_context']['conditional_memory']
        self.assertNotEqual(old_ctx['snapshot_sha256'],new_ctx['snapshot_sha256'])
        self.assertIn(self.fit_id,[e['id'] for e in old_ctx['entries']]);self.assertNotIn(self.fit_id,[e['id'] for e in new_ctx['entries']])
        self.assertEqual(server.requests[0],original)

    def test_committed_fit_recovers_after_memory_removed_without_refitting_or_new_request(self):
        self.configure();server=FakeCloud()
        with patch.object(self.loop,'_record_applied',side_effect=RuntimeError('synthetic after fit commit')):
            with self.assertRaises(RuntimeError):self.loop.run(server,max_new_requests=1)
        before=self.study.observe();db=self.memory.root/'memory.sqlite';db.rename(db.with_suffix('.temporarily-missing'))
        with patch('autoresearch.c01_research.C01Research._execute',side_effect=AssertionError('must replay fact')):
            end=C01CloudMemoryLoop(self.study.root).run(max_new_requests=0)
        self.assertEqual(end['study'],before);self.assertEqual(end['calls'][0]['status'],'applied')
        self.assertFalse(end['memory']['current_readable']);self.assertEqual(len(server.requests),1)

    def test_missing_store_blocks_uncommitted_response_and_restored_original_file_allows_offline_consumption(self):
        self.configure();server=FakeCloud()
        with patch.object(self.loop,'_consume',side_effect=RuntimeError('synthetic after receive')):
            with self.assertRaises(RuntimeError):self.loop.run(server,max_new_requests=1)
        db=self.memory.root/'memory.sqlite';backup=db.with_suffix('.temporarily-missing');db.rename(backup)
        resumed=C01CloudMemoryLoop(self.study.root)
        self.error('MEMORY_UNAVAILABLE',lambda:resumed.run(max_new_requests=0))
        self.assertEqual(resumed.status()['calls'][0]['status'],'received')
        backup.rename(db);end=resumed.run(max_new_requests=0)
        self.assertEqual(end['calls'][0]['status'],'applied');self.assertEqual(len(server.requests),1)

    def test_replaced_store_rejected_before_reservation(self):
        self.configure();db=self.memory.root/'memory.sqlite';data=db.read_bytes()
        db.rename(db.with_suffix('.original'));db.write_bytes(data)
        server=FakeCloud();self.error('MEMORY_STORE_CHANGED',lambda:self.loop.run(server,max_new_requests=1))
        self.assertEqual(server.requests,[]);self.assertEqual(self.loop.status()['budget']['requests_reserved'],0)

    def test_tampered_full_receipt_preserves_received_response_without_execution(self):
        self.configure();server=FakeCloud()
        with patch.object(self.loop,'_consume',side_effect=RuntimeError('synthetic after receive')):
            with self.assertRaises(RuntimeError):self.loop.run(server,max_new_requests=1)
        with self.loop._connect(True) as con:con.execute("UPDATE cloud_memory_uses SET snapshot_json='{}'")
        self.error('MEMORY_EVIDENCE_CHANGED',lambda:C01CloudMemoryLoop(self.study.root).run(max_new_requests=0))
        self.assertEqual(self.study.observe()['budget']['fits_used'],0);self.assertEqual(len(server.requests),1)

    def test_unknown_send_has_receipt_and_cannot_be_resent_after_memory_change(self):
        self.configure();server=FakeCloud();server.request=lambda *a,**k:(_ for _ in ()).throw(TimeoutError('synthetic unknown send'))
        self.error('NEEDS_REVIEW',lambda:self.loop.run(server,max_new_requests=1));self.retire()
        other=FakeCloud();self.error('NEEDS_REVIEW',lambda:C01CloudMemoryLoop(self.study.root).run(other,max_new_requests=1))
        end=self.loop.status();self.assertEqual(end['calls'][0]['status'],'sending')
        self.assertEqual(end['budget']['requests_reserved'],1);self.assertEqual(len(end['memory']['uses']),1)
        self.assertEqual(other.requests,[])

    def test_mismatched_inputs_recall_nothing_instead_of_loosening_scope(self):
        inputs=copy.deepcopy(self.base.inputs);inputs['source']['archive_sha256']='e'*64
        other=C01Research(self.base.root/'other-input')
        with patch('autoresearch.c01_research.c01.load_archive',return_value=inputs):
            other.create('fixture-only',self.base.index,'Synthetic scope mismatch')
        loop=C01CloudMemoryLoop(other.root,memory_workspace=self.memory.root);loop.configure(IDENTITY)
        with loop._connect() as con:spec=json.loads(con.execute('SELECT spec_json FROM project').fetchone()[0])
        context=json.loads(loop._request(other.observe(),8,[],spec)['messages'][1]['content'])['research_context']
        self.assertEqual(context['conditional_memory']['entries'],[])
        self.assertEqual(context['candidate_comparison']['included_candidate_count'],0)
        self.assertTrue(all(row['min_mae'] is None for row in context['candidate_comparison']['per_target']))

    def test_final_body_cap_and_snapshot_cap_fail_before_reservation(self):
        self.configure()
        with self.loop._connect() as con:spec=json.loads(con.execute('SELECT spec_json FROM project').fetchone()[0])
        obs=self.study.observe();base=C01CloudLoop._request(self.loop,obs,8,[],spec)
        spec['max_request_bytes']=len(canonical(base).encode('utf-8'))+100
        self.error('PROMPT_TOO_LARGE',lambda:self.loop._request(obs,8,[],spec))
        snapshot=MemoryContext(self.memory.root).snapshot(self.study);snapshot['warning']='x'*(512*1024)
        with patch.object(MemoryContext,'snapshot',return_value=snapshot):
            self.error('MEMORY_CONTEXT_TOO_LARGE',lambda:self.loop._request(obs,8,[],spec))
        self.assertEqual(self.loop.status()['budget']['requests_reserved'],0)

    def test_cli_resumes_frozen_memory_when_omitted_and_offline_mode_never_starts_transport(self):
        self.configure();resumed=cli.loop_for(self.study.root)
        self.assertIsInstance(resumed,C01CloudMemoryLoop);self.assertTrue(cli.configured(resumed))
        args=['cloud-cli','--workspace',str(self.study.root),'--output',str(self.base.root/'offline-memory'),'--max-new-requests','0']
        with patch.object(sys,'argv',args),patch.object(cli,'OwnedCloudOllama',side_effect=AssertionError('must remain offline')):
            self.assertEqual(cli.main(),0)
        self.assertEqual(resumed.status()['budget']['requests_reserved'],0)
        wrong=C01CloudMemoryLoop(self.study.root,memory_workspace=self.base.root/'different-memory')
        self.error('MEMORY_CONFIG_CHANGED',wrong.status)

    def test_explicit_memory_cannot_retrofit_a_normal_cloud_journal(self):
        C01CloudLoop(self.study.root).configure(IDENTITY)
        before=self.loop.db.read_bytes()
        self.error('CONFIG_CHANGED',lambda:cli.configured(cli.loop_for(self.study.root,memory_workspace=self.memory.root)))
        self.assertEqual(self.loop.db.read_bytes(),before)

    def test_cli_corrupt_frozen_mode_is_reported_before_any_transport(self):
        self.configure()
        with self.loop._connect(True) as con:con.execute("UPDATE project SET spec_json='{'")
        args=['cloud-cli','--workspace',str(self.study.root),'--output',str(self.base.root/'corrupt-mode'),'--max-new-requests','0']
        with patch.object(sys,'argv',args),patch.object(cli,'OwnedCloudOllama',side_effect=AssertionError('must not start')):
            self.assertEqual(cli.main(),1)
        with self.loop._connect() as con:self.assertEqual(con.execute('SELECT count(*) FROM calls').fetchone()[0],0)


class CandidateComparisonTests(unittest.TestCase):
    def test_provenance_dictionary_roundtrips_every_cell_without_changing_original_observation(self):
        original={'dataset_inspection':{'projection':{'provenance_table':{
            'columns':['sample_id','field','source','sheet','cell','raw','formula'],
            'rows':[[str(i),'x','long-original-source-path'*5,'same-sheet','A'+str(i),i,None] for i in range(64)]}}}}
        context=copy.deepcopy(original);compact_provenance(context)
        table=context['dataset_inspection']['projection']['provenance_table'];self.assertIn('dictionary_encoded_columns',table)
        encoded=copy.deepcopy(context);compact_provenance(context);self.assertEqual(context,encoded)
        decoded=copy.deepcopy(table)
        for name,values in decoded.pop('dictionary_encoded_columns').items():
            index=decoded['columns'].index(name)
            for row in decoded['rows']:row[index]=values[row[index]]
        decoded.pop('encoding')
        self.assertEqual(decoded.pop('encoding_schema'),'c01-cell-provenance-dictionary-v1')
        self.assertEqual(decoded,original['dataset_inspection']['projection']['provenance_table'])
        self.assertEqual(len(decoded['rows']),64);self.assertIsNone(decoded['rows'][0][-1])
        self.assertLess(len(canonical(table)),len(canonical(decoded)))

    def test_distinct_units_ties_and_latest_regression_do_not_erase_earlier_candidate(self):
        targets=['t1','t2','t3','t4']
        def metrics(values):return [{'target':t,'mae':v,'baseline_mae':b} for t,v,b in zip(targets,values,[2,9000,.2,30])]
        def entry(id,values):return {'id':id,'kind':'fit_observation','payload':{'recipe':{'alpha':10,'features':['x']},'metrics':metrics(values)}}
        tradeoff=entry('tradeoff',[1.1,9999,.11,40]);tradeoff['payload']['recipe']['alpha']=20
        memory={'snapshot_sha256':'f'*64,'recall_limit':8,'entries_omitted':1,'entries':[entry('early',[1,10000,.1,50]),entry('tie',[1,10000,.1,50]),tradeoff]}
        observation={'data':{'targets':targets},'actions':[{'id':'last','action':'fit','result':{'recipe':{'alpha':.1,'features':['y']},'summary':{'metrics':metrics([2,20000,.3,70])}}}]}
        original=copy.deepcopy((observation,memory));result=candidate_comparison(observation,memory)
        self.assertEqual((observation,memory),original)
        self.assertEqual(result['nondominated_included_candidate_ids'],['memory:early','memory:tie','memory:tradeoff'])
        self.assertTrue(all(r['latest_regressed'] for r in result['per_target']))
        self.assertEqual([r['min_mae'] for r in result['per_target']],[1,9999,.1,40])
        self.assertEqual(result['per_target'][0]['min_candidate_ids'],['memory:early','memory:tie'])
        self.assertFalse(result['complete_project_history']);self.assertEqual(result['memory_entries_omitted'],1)
        self.assertNotIn('score',result);self.assertNotIn('selected_recipe',result)
        self.assertEqual([r['below_own_baseline'] for r in result['per_target']],[True,False,True,False])


if __name__=='__main__':unittest.main()
