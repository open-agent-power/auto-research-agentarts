import csv
import hashlib
import io
import os
from pathlib import Path
import tempfile
import threading
import unittest

from autoresearch.c01_loop import C01Loop, LoopError, correlation_influence


def fixture():
    samples=io.StringIO(); w=csv.DictWriter(samples,fieldnames=['sample_id','water_contact_angle_deg','cell_seeding_efficiency_24h_pct']);w.writeheader()
    predictions=io.StringIO(); q=csv.DictWriter(predictions,fieldnames=['round_id','target','sample_id','observed','predicted']);q.writeheader()
    targets=['cell_seeding_efficiency_24h_pct','dna_cell_count_d21','alp_norm_d21','calcium_deposition_d21_ug_ml']
    for i in range(8):
        w.writerow({'sample_id':f'Alloy {i+1}','water_contact_angle_deg':i+1,'cell_seeding_efficiency_24h_pct':(i+1)*3})
        for target in targets:q.writerow({'round_id':'R1','target':target,'sample_id':f'Alloy {i+1}','observed':10,'predicted':8 if i else 3})
    return {'cleaned_samples.csv':samples.getvalue().encode(),'loo_predictions.csv':predictions.getvalue().encode()}


class C01LoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'continuation';self.files=fixture();self.parent=b'original manifest'
    def loop(self): return C01Loop(self.path,self.parent,self.files)
    def step(self,loop,request): return loop.step(request,loop.status()['observation_sha256'])

    def test_two_steps_replay_resume_and_stop(self):
        loop=self.loop();self.assertEqual(loop.status()['status'],'idle');self.assertFalse(self.path.exists())
        first=self.step(loop,'request_first_1234');self.assertFalse(first['replayed']);self.assertEqual(first['state']['status'],'paused')
        first_id=first['state']['actions'][0]['id'];self.assertEqual(first['state']['actions'][0]['evidence_ids'],['R1','R2'])
        restored=self.loop();self.assertTrue(self.step(restored,'request_first_1234')['replayed'])
        second=self.step(restored,'request_second_1234')['state'];self.assertEqual(second['status'],'needs_review');self.assertEqual(second['actions'][1]['evidence_ids'],[first_id]);self.assertAlmostEqual(second['actions'][1]['result']['pearson_r'],1.0)
        with self.assertRaises(LoopError) as caught:self.step(restored,'request_third_1234')
        self.assertEqual(caught.exception.code,'BUDGET_EXHAUSTED');self.assertEqual(len(restored.status()['actions']),2)

    def test_parent_and_input_identity_are_bound(self):
        self.step(self.loop(),'request_first_1234')
        with self.assertRaises(LoopError):C01Loop(self.path,b'other manifest',self.files).status()
        bad={**self.files,'cleaned_samples.csv':b'changed'}
        with self.assertRaises(LoopError):C01Loop(self.path,self.parent,bad).status()

    def test_existing_unmanaged_file_is_never_adopted(self):
        self.path.mkdir(); db=self.path/'continuation.sqlite3';db.write_bytes(b'other user data');before=hashlib.sha256(db.read_bytes()).digest()
        with self.assertRaises(LoopError):self.loop().status()
        self.assertEqual(hashlib.sha256(db.read_bytes()).digest(),before)

    def test_hardlink_to_existing_db_rejected(self):
        self.path.mkdir();outside=Path(self.tmp.name)/'other.sqlite3';outside.write_bytes(b'other user data');os.link(outside,self.path/'continuation.sqlite3')
        with self.assertRaises(LoopError):self.loop().status()
        self.assertEqual(outside.read_bytes(),b'other user data')

    def test_same_request_concurrent_only_once(self):
        # Initialize one step then race the same ID from two independent instances.
        self.step(self.loop(),'request_first_1234');results=[];fail=[]
        observed=self.loop().status()['observation_sha256']
        def run():
            try:results.append(self.loop().step('request_second_1234',observed))
            except Exception as exc:fail.append(exc)
        threads=[threading.Thread(target=run) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(fail,[]);self.assertEqual(sorted(r['replayed'] for r in results),[False,True]);self.assertEqual(len(self.loop().status()['actions']),2)

    def test_degenerate_pair_stops_without_writes(self):
        raw=b'sample_id,water_contact_angle_deg,cell_seeding_efficiency_24h_pct\n'+b''.join(f'{i},1,{i}\n'.encode() for i in range(8))
        with self.assertRaises(LoopError):correlation_influence(raw)

    def test_stale_observation_rejected_without_second_action(self):
        loop=self.loop();old=loop.status()['observation_sha256'];loop.step('request_first_1234',old)
        with self.assertRaises(LoopError) as caught:loop.step('request_second_1234',old)
        self.assertEqual(caught.exception.code,'STALE_OBSERVATION');self.assertEqual(len(loop.status()['actions']),1)

    def test_first_stale_request_does_not_break_initialization(self):
        loop=self.loop();good=loop.status()['observation_sha256']
        with self.assertRaises(LoopError) as caught:loop.step('request_stale_1234','0'*64)
        self.assertEqual(caught.exception.code,'STALE_OBSERVATION')
        self.assertEqual(loop.status()['status'],'idle')
        self.assertEqual(loop.step('request_first_1234',good)['state']['status'],'paused')


if __name__=='__main__': unittest.main()
