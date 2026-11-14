"""Durability and boundedness with fake callbacks; never executes a study."""
import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest

from autoresearch.bounded_study_ledger import BoundedStudyLedger
from autoresearch.contracts import ResearchError, fingerprint


def limits():
    return {'generate': 2, 'warmup': 1, 'timed': 1, 'correctness': 1,
            'oracle': 1, 'bruteforce': 1, 'audit': 1, 'primary': 1,
            'kernel_total': 3, 'scan_comparisons': 9, 'exhaustive_subsets': 1}


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger = BoundedStudyLedger(self.root/'global-claims', 'study-fixture')
        self.binding = {'study_id':'study-fixture', 'output_root':str(self.root/'result'),
                        'request_id':'request-fixture', 'protocol_sha256':'a'*64,
                        'code_commit':'b'*40, 'runtime_identity':'c'*64}
        self.ledger.claim(self.binding, limits())
        worker = self.ledger.worker()
        worker.__enter__()
        self.addCleanup(worker.__exit__, None, None, None)
        self.ledger.start_generation(now_ns=0, boot_id='fixture-boot')

    def gen(self, number):
        return self.ledger.perform('gen-'+str(number), 'generate', {'case_id':'case-'+str(number)},
                                   lambda: {'jobs': [[0, 1, 2, number]]}, boot_id='fixture-boot', clock=lambda: 1)

    def prepare(self):
        self.gen(1); self.gen(2)
        self.ledger.finish_generation('d'*64, now_ns=2, boot_id='fixture-boot')
        self.ledger.seal_inputs('d'*64, 'e'*64)
        self.ledger.start_primary(now_ns=3, boot_id='fixture-boot')

    def kernel(self, op_id, kind, n=3, arm='fixed_scan'):
        return self.ledger.perform(op_id, kind, {'n':n, 'arm':arm}, lambda: {'fake':op_id}, boot_id='fixture-boot', clock=lambda: 4)

    def assert_code(self, code, callback, *args, **kwargs):
        with self.assertRaises(ResearchError) as caught:
            callback(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_claim_replay_and_copied_root_or_protocol_conflicts(self):
        self.assertTrue(self.ledger.claim(self.binding, limits())['replayed'])
        for key,value in (('output_root',str(self.root/'copied')),('protocol_sha256','f'*64),('code_commit','d'*40)):
            altered = dict(self.binding, **{key:value})
            self.assert_code('STUDY_CONFLICT', self.ledger.claim, altered, limits())
        self.assert_code('STUDY_CONFLICT', self.ledger.claim, self.binding, dict(limits(), generate=3))

    def test_reservation_durable_before_callback_and_replay_does_not_run(self):
        observed=[]
        def callback():
            con=sqlite3.connect(self.ledger.db.as_uri()+'?mode=ro', uri=True)
            try: observed.append(con.execute('SELECT count(*) FROM events').fetchone()[0])
            finally: con.close()
            return {'result':'saved'}
        first=self.ledger.perform('generate-one','generate',{'case_id':'case-one'},callback, boot_id='fixture-boot', clock=lambda:1)
        second=self.ledger.perform('generate-one','generate',{'case_id':'case-one'},lambda: self.fail('replayed callback'), boot_id='fixture-boot', clock=lambda:1)
        self.assertEqual(observed,[1])
        self.assertEqual((first['replayed'],second['replayed']),(False,True))
        self.assertEqual(first['result'],second['result'])
        snap=self.ledger.snapshot()
        self.assertEqual(snap['counts']['generate'],1)
        self.assertEqual([x['event']['event'] for x in snap['events']],['reserved','completed'])
        self.assertEqual(snap['events'][1]['event']['reservation_sha256'],snap['events'][0]['sha256'])
        self.assert_code('STUDY_CONFLICT',self.ledger.perform,'generate-one','generate',{'case_id':'other'},lambda:None)

    def test_callback_and_replay_cannot_mutate_reserved_spec_or_cached_result(self):
        spec={'case_id':'fixture','labels':['original']}
        def callback():
            spec['labels'].append('changed-by-callback')
            return {'saved':[1]}
        self.ledger.perform('gen-alias','generate',spec,callback,boot_id='fixture-boot',clock=lambda:1)
        original={'case_id':'fixture','labels':['original']}
        receipt=self.ledger.perform('gen-alias','generate',original,lambda:self.fail('no replay'),boot_id='fixture-boot',clock=lambda:1)
        receipt['result']['saved'].append(2)
        again=self.ledger.perform('gen-alias','generate',original,lambda:self.fail('no replay'),boot_id='fixture-boot',clock=lambda:1)
        self.assertEqual(again['result'],{'saved':[1]})
        self.assertEqual(self.ledger.snapshot()['events'][0]['event']['spec'],original)

    def test_lost_receipt_is_unknown_and_never_reexecuted(self):
        def lost(): raise KeyboardInterrupt('simulated crash')
        with self.assertRaises(KeyboardInterrupt): self.ledger.perform('gen-unknown','generate',{'case_id':'x'},lost, boot_id='fixture-boot', clock=lambda:1)
        snap=self.ledger.snapshot()
        self.assertEqual(snap['unknown'],['gen-unknown'])
        self.assertEqual(snap['counts']['generate'],1)
        self.assert_code('STUDY_UNKNOWN',self.ledger.perform,'gen-unknown','generate',{'case_id':'x'},lambda:self.fail('repeated'))
        self.assert_code('STUDY_UNKNOWN',self.ledger.perform,'gen-other','generate',{'case_id':'y'},lambda:self.fail('new call'))
        self.assert_code('STUDY_TIMEOUT',self.ledger.seal_inputs,'d'*64,'e'*64)

    def test_failed_callback_consumes_budget_and_stops_all_future_calls(self):
        def fail(): raise ValueError('fixture error')
        self.assert_code('STUDY_FAILED',self.ledger.perform,'gen-fail','generate',{'case_id':'x'},fail, boot_id='fixture-boot', clock=lambda:1)
        snap=self.ledger.snapshot()
        self.assertEqual(snap['failed'],['gen-fail'])
        self.assertEqual(snap['counts']['generate'],1)
        self.assert_code('STUDY_FAILED',self.ledger.perform,'gen-fail','generate',{'case_id':'x'},lambda:None)
        self.assert_code('STUDY_UNKNOWN',self.ledger.perform,'gen-other','generate',{'case_id':'y'},lambda:None)

    def test_two_review_phases_budget_and_full_receipts(self):
        self.assert_code('STUDY_NOT_REVIEWED',self.ledger.start_primary,now_ns=3,boot_id='fixture-boot')
        self.gen(1)
        self.assert_code('STUDY_TIMEOUT',self.ledger.seal_inputs,'d'*64,'e'*64)
        self.gen(2)
        self.ledger.finish_generation('d'*64,now_ns=2,boot_id='fixture-boot')
        phase=self.ledger.seal_inputs('d'*64,'e'*64)
        self.assertFalse(phase['replayed'])
        self.assertEqual(phase['phase']['after_ordinal'],4)
        self.ledger.start_primary(now_ns=3,boot_id='fixture-boot')
        self.kernel('warm','warmup');self.kernel('timed','timed');self.kernel('correct','correctness')
        self.assert_code('STUDY_BUDGET',self.kernel,'extra','timed')
        self.ledger.perform('oracle','oracle',{},lambda:{'objective':1},boot_id='fixture-boot',clock=lambda:4)
        self.ledger.perform('brute','bruteforce',{'n':0},lambda:{'objective':1},boot_id='fixture-boot',clock=lambda:4)
        snap=self.ledger.snapshot()
        self.assertEqual(snap['counts']['kernel_total'],3)
        self.assertEqual(snap['counts']['scan_comparisons'],9)
        self.assertEqual(snap['phases']['primary']['after_ordinal'],4)
        self.assertTrue(self.ledger.seal_inputs('d'*64,'e'*64)['replayed'])
        self.assertTrue(self.ledger.start_primary(now_ns=5,boot_id='fixture-boot')['replayed'])
        self.ledger.finish_primary('f'*64,now_ns=5,boot_id='fixture-boot')
        self.ledger.perform('audit','audit',{},lambda:{'saved_only':True},boot_id='fixture-boot',clock=lambda:6)
        self.assertTrue(self.ledger.finish_primary('f'*64,now_ns=5,boot_id='fixture-boot')['replayed'])
        self.assert_code('STUDY_CONFLICT',self.ledger.finish_primary,'0'*64,now_ns=5,boot_id='fixture-boot')
        snap=self.ledger.snapshot()
        self.assertEqual(snap['counts']['audit'],1)
        self.assertEqual(snap['phases']['primary_result']['after_ordinal'],14)
        self.assertEqual(snap['unknown'],[])

    def test_non_json_callback_result_is_retained_as_failure_and_not_repeated(self):
        self.assert_code('STUDY_FAILED',self.ledger.perform,'gen-nan','generate',{'case_id':'fixture'},
                         lambda:{'value':float('nan')},boot_id='fixture-boot',clock=lambda:1)
        snap=self.ledger.snapshot()
        self.assertEqual(snap['failed'],['gen-nan'])
        self.assertIn('nan',snap['events'][-1]['event']['result']['returned_result_repr'])
        self.assert_code('STUDY_FAILED',self.ledger.perform,'gen-nan','generate',{'case_id':'fixture'},lambda:self.fail('no replay'))

    def test_missing_db_and_tampered_chain_fail_closed(self):
        self.gen(1)
        con=sqlite3.connect(self.ledger.db)
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute("UPDATE events SET record=? WHERE ordinal=1", ('{}',))
        with con:
            con.execute("DROP TRIGGER events_no_update")
            con.execute("UPDATE events SET record=? WHERE ordinal=1", ('{}',))
        con.close()
        self.assert_code('EVIDENCE_CHANGED',self.ledger.snapshot)
        second=BoundedStudyLedger(self.root/'other','study-other')
        second.claim(dict(self.binding,study_id='study-other'),limits())
        second.db.unlink()
        self.assert_code('STUDY_UNKNOWN',second.claim,dict(self.binding,study_id='study-other'),limits())

    def test_exhaustive_subsets_are_reserved_and_cannot_exceed_budget(self):
        self.prepare()
        self.assert_code('STUDY_BUDGET',self.ledger.perform,'brute-excess','bruteforce',{'n':1},lambda:self.fail('no call'),
                         boot_id='fixture-boot',clock=lambda:4)
        self.assertEqual(self.ledger.snapshot()['counts']['exhaustive_subsets'],0)
        self.ledger.perform('brute-ok','bruteforce',{'n':0},lambda:{'objective':0},boot_id='fixture-boot',clock=lambda:4)
        self.assertEqual(self.ledger.snapshot()['counts']['exhaustive_subsets'],1)

    def test_elapsed_budget_boot_change_and_expiry_after_reservation_fail_closed(self):
        self.assert_code('STUDY_CLOCK_CHANGED',self.ledger.perform,'gen-wrong','generate',{},lambda:self.fail('no call'),
                         boot_id='other-boot',clock=lambda:1)
        self.assertIsNotNone(self.ledger.snapshot()['halted'])
        self.assertEqual(self.ledger.snapshot()['counts']['generate'],0)
        for scenario in ('before','after'):
            ledger=BoundedStudyLedger(self.root/scenario,'study-'+scenario)
            ledger.claim({'study_id':'study-'+scenario},limits())
            with ledger.worker():
                ledger.start_generation(now_ns=0,boot_id='fixture')
                clock=iter((120_000_000_000,)) if scenario=='before' else iter((119_999_999_999,120_000_000_000))
                code='STUDY_TIMEOUT' if scenario=='before' else 'STUDY_CLOCK_CHANGED'
                self.assert_code(code,ledger.perform,'gen-late','generate',{},lambda:self.fail('no call'),
                                 boot_id='fixture',clock=lambda:next(clock))
                snap=ledger.snapshot()
                self.assertIsNotNone(snap['halted'])
                self.assertEqual(snap['counts']['generate'],0 if scenario=='before' else 1)
                self.assertEqual(snap['unknown'],[] if scenario=='before' else ['gen-late'])

    def test_clock_reversal_after_callback_preserves_result_as_unknown(self):
        clock=iter((5,6,4))
        self.assert_code('STUDY_CLOCK_CHANGED',self.ledger.perform,'gen-reversed','generate',{'case_id':'x'},
                         lambda:{'saved':[1]},boot_id='fixture-boot',clock=lambda:next(clock))
        snap=self.ledger.snapshot()
        self.assertEqual(snap['unknown'],['gen-reversed'])
        self.assertEqual(snap['halted']['context']['returned_result'],{'saved':[1]})
        self.assertEqual(snap['events'][0]['event']['monotonic_ns'],5)
        self.assertEqual(len(snap['events']),1)
        self.assert_code('STUDY_UNKNOWN',self.ledger.perform,'gen-reversed','generate',{'case_id':'x'},lambda:self.fail('no replay'))

    def test_clock_reversal_between_completed_calls_latches_without_reservation(self):
        self.ledger.perform('gen-first','generate',{'case_id':'x'},lambda:{'saved':1},
                            boot_id='fixture-boot',clock=lambda:10)
        self.assert_code('STUDY_CLOCK_CHANGED',self.ledger.perform,'gen-next','generate',{'case_id':'y'},lambda:self.fail('no call'),
                         boot_id='fixture-boot',clock=lambda:9)
        snap=self.ledger.snapshot()
        self.assertEqual(snap['counts']['generate'],1)
        self.assertEqual(len(snap['events']),2)
        self.assertIsNotNone(snap['halted'])
        self.assertEqual([x['event']['monotonic_ns'] for x in snap['events']],[10,10])

    def test_phase_timer_resume_and_terminal_halt_preserve_receipts(self):
        self.gen(1);self.gen(2)
        self.ledger.finish_generation('d'*64,now_ns=10,boot_id='fixture-boot')
        self.ledger.seal_inputs('d'*64,'e'*64)
        first=self.ledger.start_primary(now_ns=100,boot_id='fixture-boot')
        replay=self.ledger.start_primary(now_ns=200,boot_id='fixture-boot')
        self.assertEqual(first['phase'],replay['phase'])
        self.assertEqual(first['phase']['deadline_monotonic_ns'],100+120_000_000_000-10)
        self.assert_code('STUDY_CLOCK_CHANGED',self.ledger.start_primary,now_ns=200,boot_id='other-boot')
        self.ledger.halt(reason='Saved feasibility failed',context={'op_id':'existing'})
        self.assert_code('STUDY_FAILED',self.ledger.perform,'never','warmup',{'n':3,'arm':'fixed_scan'},lambda:self.fail('no call'),
                         boot_id='fixture-boot',clock=lambda:201)
        self.assertEqual(self.ledger.snapshot()['halted']['reason'],'Saved feasibility failed')

    def test_only_one_worker_and_status_does_not_create_claim(self):
        untouched=BoundedStudyLedger(self.root/'absent','study-absent')
        self.assert_code('STUDY_NOT_FOUND',untouched.snapshot)
        self.assertFalse((self.root/'absent').exists())
        second=BoundedStudyLedger(self.ledger.root,'study-second')
        second.claim(dict(self.binding,study_id='study-second'),limits())
        self.assert_code('STUDY_WORKER_REQUIRED',second.perform,'gen-x','generate',{},lambda:None)
        with self.assertRaises(ResearchError) as caught:
            with second.worker(): pass
        self.assertEqual(caught.exception.code,'STUDY_BUSY')

    def test_symlink_claim_root_refused(self):
        redirected=self.root/'redirected';redirected.symlink_to(self.ledger.root,target_is_directory=True)
        self.assert_code('UNSAFE_PATH',BoundedStudyLedger,redirected,'study-fixture')


if __name__ == '__main__': unittest.main()
