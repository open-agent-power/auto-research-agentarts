"""Fake-only bounded scheduler harness checks; never generate jobs or solve."""
from copy import deepcopy
import importlib.util
import json
import time
from contextlib import ExitStack
import itertools
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import scheduling_threshold_policy as policy, scheduling_kernel as kernel
from autoresearch.bounded_study_ledger import BoundedStudyLedger, _charge, _subsets
from autoresearch.contracts import ResearchError, fingerprint

PATH = Path(__file__).resolve().parents[1]/'scripts/run_scheduling_policy_transfer.py'
SPEC = importlib.util.spec_from_file_location('scheduling_policy_runner_test', PATH)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class PolicyTransferTests(unittest.TestCase):
    def test_all_arms_share_dispatch_and_fixed_threshold_with_fake_kernel(self):
        observed=[]
        def fake_schedule(jobs, method):
            observed.append((len(jobs),method))
            return {'method':method}
        with patch.object(kernel,'schedule',side_effect=fake_schedule), \
             patch.object(kernel,'jobs_for',side_effect=AssertionError('No job generation')), \
             patch.object(kernel,'brute_force',side_effect=AssertionError('No solve')):
            for n in (0,31,32,33,64):
                jobs=[None]*n
                for arm in policy.ARMS:
                    result=policy.dispatch(jobs,arm)
                    self.assertEqual(result['method'],policy.method_for(arm,n))
        self.assertEqual([method for n,method in observed if n==32],['binary_search_dp','quadratic_scan_dp','quadratic_scan_dp'])
        self.assertEqual([method for n,method in observed if n==33],['binary_search_dp','quadratic_scan_dp','binary_search_dp'])
        for arm,n in (('other',1),('threshold32',True),('threshold32',-1)):
            with self.assertRaises(ValueError):policy.method_for(arm,n)

    def test_fake_clock_preserves_zero_negative_nonfinite_without_retry(self):
        for values,status,raw,expected in (((10,15),'ok',5,5), ((10,10),'zero',0,None),
                                            ((10,9),'negative',-1,None), ((0,float('inf')),'nonfinite','Infinity',None),
                                            ((float('nan'),1),'nonfinite','NaN',None)):
            seq=iter(values)
            with self.subTest(status=status), patch.object(kernel,'schedule',return_value={'saved':'fixture'}) as schedule:
                result=policy.measured([], 'fixed_binary', clock=lambda:next(seq))
                self.assertEqual((result['timing_status'],result['elapsed_raw'],result['elapsed_ns']),(status,raw,expected))
                self.assertEqual(schedule.call_count,1)
                runner._check_timing(result)

    def test_full_plan_is_fixed_order_and_never_generates_inputs(self):
        cases=[{**case,'jobs_sha256':'a'*64} for case in runner.case_descriptors()]
        with patch.object(kernel,'jobs_for',side_effect=AssertionError('No generation')), \
             patch.object(kernel,'schedule',side_effect=AssertionError('No solve')), \
             patch.object(kernel,'brute_force',side_effect=AssertionError('No solve')):
            plan=runner.operation_plan(cases)
        self.assertEqual(len(plan),1200)
        self.assertEqual(plan[0][0],'gen-correct-n8-seed601')
        self.assertEqual(plan[1][0],'gen-correct-n12-seed601')
        self.assertEqual([item[0] for item in plan[29:34]],['oracle-correct-n8-seed601','correct-correct-n8-seed601-00',
            'correct-correct-n8-seed601-01','correct-correct-n8-seed601-02','brute-correct-n8-seed601'])
        timed=[spec for _,kind,spec in plan if kind=='timed' and spec['case_id']=='perf-n16-seed601']
        self.assertEqual(len(timed),36)
        self.assertEqual([item['arm'] for item in timed[:18]], [arm for perm in itertools.permutations(policy.ARMS) for arm in perm])
        self.assertEqual([item['position'] for item in timed],list(range(36)))
        self.assertEqual([item['block'] for item in timed],[0]*18+[1]*18)
        self.assertEqual(sum(_charge(kind,spec) for _,kind,spec in plan),6080234)
        self.assertEqual(sum(_subsets(kind,spec) for _,kind,spec in plan),4352)
        self.assertEqual(sum(case['n'] for case in runner.case_descriptors()),2642)

    def test_prefix_detects_reordering_wrong_spec_and_pending_without_callbacks(self):
        plan=runner.operation_plan()
        events=[]
        for op,kind,spec in plan[:2]:
            events.extend([{'event':{'event':'reserved','op_id':op,'operation':kind,'spec':spec}},
                           {'event':{'event':'completed'}}])
        snapshot={'events':events,'unknown':[],'failed':[],'halted':None}
        runner._expect_prefix(snapshot,plan)
        for modify in ('order','spec','unknown','failed','halted'):
            bad=deepcopy(snapshot)
            if modify=='order':bad['events'][0]['event']['op_id']='gen-wrong'
            if modify=='spec':bad['events'][0]['event']['spec']['seed']=999
            if modify=='unknown':bad['unknown']=['uncertain']
            if modify=='failed':bad['failed']=['failed']
            if modify=='halted':bad['halted']={'reason':'failed'}
            with self.subTest(modify=modify),self.assertRaises(ResearchError):runner._expect_prefix(bad,plan)

    def test_saved_timing_arithmetic_marks_zero_warmup_and_timed_uninterpretable(self):
        cases=runner.case_descriptors();events=[]
        for case in cases:
            if case['kind']!='performance':continue
            for arm in policy.ARMS:
                for i in range(12):
                    events.append({'event':{'event':'completed','operation':'timed',
                        'op_id':f"{case['case_id']}-{arm}-{i}", 'spec':{'case_id':case['case_id'],'arm':arm},
                        'result':{'timing_status':'ok','elapsed_ns':100 if arm!='threshold32' else 90}}})
        result=runner._summarize(cases,events)
        self.assertTrue(result['primary_timing_interpretable'])
        self.assertEqual(result['primary_policy_over_binary'],.9)
        first=next(c for c in cases if c['kind']=='performance')
        events.append({'event':{'event':'completed','operation':'warmup','op_id':'invalid-warm',
                       'spec':{'case_id':first['case_id']},'result':{'timing_status':'zero','elapsed_ns':None}}})
        invalid=runner._summarize(cases,events)
        self.assertFalse(invalid['primary_timing_interpretable'])
        self.assertIsNone(invalid['primary_policy_over_binary'])
        self.assertEqual(invalid['performance_cases'][0]['invalid_warmups'],['invalid-warm'])
        self.assertEqual(len(invalid['performance_cases']),27)

    def test_independent_validator_and_harness_plans_and_saved_summary_agree_without_jobs(self):
        verifier_path=Path(__file__).resolve().parents[1]/'scripts/verify_scheduling_policy_transfer.py'
        spec=importlib.util.spec_from_file_location('fake_saved_crosscheck_verifier',verifier_path)
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        cases=[{**case,'jobs_sha256':'a'*64} for case in runner.case_descriptors()]
        case_map={case['case_id']:case for case in cases}
        with patch.object(verifier,'fenwick_optimum',side_effect=AssertionError('No oracle')), \
             patch.object(kernel,'jobs_for',side_effect=AssertionError('No generator')), \
             patch.object(kernel,'schedule',side_effect=AssertionError('No solver')):
            self.assertEqual(runner.operation_plan(cases),list(verifier._expected_operations(case_map)))
            events=[];observations={}
            for case in cases:
                if case['kind']!='performance':continue
                times={arm:[10]*12 for arm in policy.ARMS}
                observations[case['case_id']]={'timed':times,'invalid_warmups':[]}
                for arm in policy.ARMS:
                    for i,value in enumerate(times[arm]):
                        events.append({'event':{'event':'completed','operation':'timed','op_id':str(i),
                                       'spec':{'case_id':case['case_id'],'arm':arm},
                                       'result':{'timing_status':'ok','elapsed_ns':value}}})
            self.assertEqual(runner._summarize(cases,events),verifier._summarize_saved(case_map,observations))

    def test_fake_correctness_case_uses_only_reserved_fixed_callbacks(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger=BoundedStudyLedger(Path(temp),'study-fixture')
            budget={'generate':0,'warmup':0,'timed':0,'correctness':3,'oracle':1,'bruteforce':1,
                    'audit':0,'primary':1,'kernel_total':3,'scan_comparisons':0,'exhaustive_subsets':2}
            ledger.claim({'study_id':'study-fixture'},budget)
            with ledger.worker():
                ledger.start_generation(now_ns=0,boot_id='fixture')
                ledger.finish_generation('a'*64,now_ns=1,boot_id='fixture')
                ledger.seal_inputs('a'*64,'b'*64)
                ledger.start_primary(now_ns=2,boot_id='fixture')
                case={'case_id':'correct-fixture','kind':'correctness','n':1,'seed':601,
                      'jobs':[[0,1,1,0]],'jobs_sha256':fingerprint([[0,1,1,0]])}
                class FakeOracle:
                    def fenwick_optimum(self,jobs):
                        self.saved=jobs
                        return 1
                oracle=FakeOracle()
                def fake_dispatch(jobs,arm):
                    method=policy.method_for(arm,len(jobs))
                    return {'objective':1,'schedule':[0],'full_scan_comparisons':0,
                        'operations':{'dp_steps':1,'full_scan_comparisons':0,'bisect_calls':1 if method=='binary_search_dp' else 0,
                                      'bisect_internal_comparisons':None,'reconstruction_steps':1}}
                with patch.object(kernel,'jobs_for',side_effect=AssertionError('No generator')), \
                     patch.object(kernel,'schedule',side_effect=AssertionError('No solver')), \
                     patch.object(kernel,'brute_force',return_value=1) as brute, \
                     patch.object(policy,'dispatch',side_effect=fake_dispatch) as dispatch, \
                     patch('autoresearch.bounded_study_ledger.time.monotonic_ns',return_value=3):
                    runner._run_case(ledger,case,oracle,'fixture')
                self.assertEqual((dispatch.call_count,brute.call_count),(3,1))
                self.assertEqual(oracle.saved,[{'start':0,'end':1,'weight':1,'id':0}])
                snapshot=ledger.snapshot()
                self.assertEqual((snapshot['counts']['correctness'],snapshot['counts']['oracle'],snapshot['counts']['bruteforce']),(3,1,1))
                self.assertEqual(len(snapshot['events']),10)

    def test_saved_wrong_objective_stops_after_receipt_without_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger=BoundedStudyLedger(Path(temp),'study-failure')
            budget={'generate':0,'warmup':0,'timed':0,'correctness':3,'oracle':1,'bruteforce':1,
                    'audit':0,'primary':1,'kernel_total':3,'scan_comparisons':0,'exhaustive_subsets':2}
            ledger.claim({'study_id':'study-failure'},budget)
            with ledger.worker():
                ledger.start_generation(now_ns=0,boot_id='fixture')
                ledger.finish_generation('a'*64,now_ns=1,boot_id='fixture')
                ledger.seal_inputs('a'*64,'b'*64)
                ledger.start_primary(now_ns=2,boot_id='fixture')
                case={'case_id':'correct-fixture','kind':'correctness','n':1,'seed':601,
                      'jobs':[[0,1,1,0]],'jobs_sha256':fingerprint([[0,1,1,0]])}
                class FakeOracle:
                    def fenwick_optimum(self,jobs):return 2
                returned={'objective':1,'schedule':[0],'full_scan_comparisons':0,
                    'operations':{'dp_steps':1,'full_scan_comparisons':0,'bisect_calls':1,
                                  'bisect_internal_comparisons':None,'reconstruction_steps':1}}
                with patch.object(kernel,'jobs_for',side_effect=AssertionError('No generator')), \
                     patch.object(kernel,'schedule',side_effect=AssertionError('No solver')), \
                     patch.object(kernel,'brute_force',side_effect=AssertionError('Must stop')), \
                     patch.object(policy,'dispatch',return_value=returned) as dispatch, \
                     patch('autoresearch.bounded_study_ledger.time.monotonic_ns',return_value=3):
                    with self.assertRaises(ResearchError) as caught:runner._run_case(ledger,case,FakeOracle(),'fixture')
                self.assertEqual(caught.exception.code,'STUDY_FAILED')
                self.assertEqual(dispatch.call_count,1)
                snapshot=ledger.snapshot()
                self.assertIsNotNone(snapshot['halted'])
                self.assertEqual(snapshot['counts']['correctness'],1)
                self.assertEqual(snapshot['events'][-1]['event']['result']['returned'],returned)
                self.assertEqual(snapshot['counts']['bruteforce'],0)

    def test_complete_isolated_fake_lifecycle_and_readonly_replay(self):
        # All callbacks below are fabricated deterministic fixtures; none calls the original generator/solvers.
        verifier_path=Path(__file__).resolve().parents[1]/'scripts/verify_scheduling_policy_transfer.py'
        verifier_spec=importlib.util.spec_from_file_location('fake_lifecycle_verifier',verifier_path)
        verifier=importlib.util.module_from_spec(verifier_spec);verifier_spec.loader.exec_module(verifier)
        protocol,_=runner._fixed_protocol()
        real_started=time.time()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);output=root/'output';claims=root/'claims';reviews=root/'reviews';worker=root/'autonomy'/'research-worker.lock'
            reviews.mkdir();worker.parent.mkdir()
            runtime={'python_version':'fake Python','python_executable':'/fake/python','python_implementation':'fixture',
                     'dependencies':{'numpy':'fake','scipy':'fake','scikit-learn':'fake'},'native_code_identity':'c'*64,
                     'boot_id':'a'*36,'perf_counter':{'implementation':'fake','monotonic':True,'adjustable':False,'resolution':1e-9},
                     'gc_enabled':True,'cpu_affinity':[0],'thread_environment':{k:'1' for k in runner.THREAD_KEYS}}
            sources={name:'d'*64 for name in runner.SOURCE_FILES};sources[runner.PROTOCOL_RELATIVE]='a'*64
            expected={'protocol_sha256':'a'*64,'code_commit':'b'*40,'output_root':str(output),
                      'budget_sha256':fingerprint(protocol['budget']),'source_fingerprints':sources,'runtime':runtime}
            setup={**expected,'schema_version':'scheduling-policy-setup-review-v1','status':'approved',
                   'reviewer':'fake reviewer','study_id':runner.STUDY_ID,'request_id':runner.PREPARE_ID,
                   'allowed_phase':'generate_only','limitations':['Hand-authored test approval; no real study.']}
            (reviews/'setup-review.json').write_text(json.dumps(setup),encoding='utf-8')
            def fake_generate(seed,n):
                return [(i*2,i*2+1,1,i) for i in range(n)]
            def fake_schedule(jobs,method):
                n=len(jobs);scan=n*(n-1)//2 if method=='quadratic_scan_dp' else 0
                return {'objective':n,'schedule':list(range(n)),'full_scan_comparisons':scan,
                        'operations':{'dp_steps':n,'full_scan_comparisons':scan,
                                      'bisect_calls':n if method=='binary_search_dp' else 0,
                                      'bisect_internal_comparisons':None,'reconstruction_steps':n}}
            monotonic=itertools.count(100); perf=itertools.count(1000,10)
            with ExitStack() as guard:
                for key,value in (('MAIN_ROOT',root),('OUTPUT',output),('CLAIMS',claims),('REVIEWS',reviews),('WORKER',worker)):
                    guard.enter_context(patch.object(runner,key,value))
                guard.enter_context(patch.object(runner,'_environment',return_value=(protocol,expected)))
                guard.enter_context(patch.object(runner,'_same_environment',return_value=protocol))
                guard.enter_context(patch.object(runner,'_protected',return_value=None))
                guard.enter_context(patch.object(runner,'_validator',return_value=verifier))
                guard.enter_context(patch.object(verifier,'_OUTPUT_ROOT',str(output)))
                guard.enter_context(patch.object(verifier,'_frozen_protocol_and_sources',return_value=protocol))
                guard.enter_context(patch.object(verifier,'_verify_original_source',return_value=None))
                guard.enter_context(patch.object(runner.time,'monotonic_ns',side_effect=lambda:next(monotonic)))
                guard.enter_context(patch.object(policy.time,'perf_counter_ns',side_effect=lambda:next(perf)))
                generator=guard.enter_context(patch.object(kernel,'jobs_for',side_effect=fake_generate))
                scheduler=guard.enter_context(patch.object(kernel,'schedule',side_effect=fake_schedule))
                brute=guard.enter_context(patch.object(kernel,'brute_force',side_effect=lambda jobs:len(jobs)))
                oracle=guard.enter_context(patch.object(verifier,'fenwick_optimum',side_effect=lambda jobs:len(jobs)))
                audit=guard.enter_context(patch.object(verifier,'verify_primary_result',wraps=verifier.verify_primary_result))
                # Inject a crash after the manifest was atomically written, before its phase receipt.
                with patch.object(BoundedStudyLedger,'finish_generation',side_effect=RuntimeError('injected phase receipt loss')):
                    with self.assertRaisesRegex(RuntimeError,'injected phase receipt loss'):runner.prepare()
                before=runner.status()
                self.assertTrue((output/'inputs.json').is_file())
                self.assertIsNone(before['phases']['generation_result'])
                deadline=before['phases']['generation']['deadline_monotonic_ns']
                self.assertEqual(generator.call_count,29)
                prepared=runner.resume()
                self.assertEqual(prepared['status'],'prepared')
                self.assertEqual(generator.call_count,29)
                self.assertEqual(runner.status()['phases']['generation']['deadline_monotonic_ns'],deadline)
                self.assertEqual(runner.resume()['status'],'awaiting_input_review')
                self.assertEqual((scheduler.call_count,brute.call_count,oracle.call_count),(0,0,0))
                self.assertEqual(runner.status()['counts']['generate'],29)
                with self.assertRaises(ResearchError) as caught:runner.run_primary()
                self.assertEqual(caught.exception.code,'STUDY_NOT_REVIEWED')
                self.assertEqual((scheduler.call_count,brute.call_count,oracle.call_count),(0,0,0))
                input_review={**expected,'schema_version':'scheduling-policy-input-review-v1','status':'approved',
                    'reviewer':'fake reviewer','study_id':runner.STUDY_ID,'request_id':runner.PRIMARY_ID,
                    'allowed_phase':'primary_and_saved_audit','limitations':['Hand-authored test approval; no real study.'],
                    'inputs_sha256':prepared['inputs_sha256'],'shared_claim_sha256':prepared['claim_sha256']}
                (reviews/'input-review.json').write_text(json.dumps(input_review),encoding='utf-8')
                primary=runner.run_primary()
                self.assertEqual(primary['status'],'completed')
                self.assertEqual((scheduler.call_count,brute.call_count,oracle.call_count),(1140,2,29))
                audited=runner.verify()
                self.assertEqual(audited['audit']['status'],'passed')
                self.assertEqual(audit.call_count,1)
                self.assertTrue(runner.prepare()['replayed'])
                self.assertTrue(runner.run_primary()['replayed'])
                self.assertTrue(runner.resume()['replayed'])
                self.assertTrue(runner.verify()['replayed'])
                self.assertEqual((generator.call_count,scheduler.call_count,brute.call_count,oracle.call_count,audit.call_count),(29,1140,2,29,1))
                saved=runner.status()
                self.assertEqual((saved['counts']['kernel_total'],saved['counts']['exhaustive_subsets'],saved['counts']['audit']),(1140,4352,1))
                self.assertEqual((saved['unknown'],saved['failed'],saved['halted']),([],[],None))
        print('FAKE_LIFECYCLE_SECONDS',round(time.time()-real_started,3),flush=True)

    def test_phase_clock_failure_latches_without_running_a_callback(self):
        class FakeLedger:
            def __init__(self):self.saved=None
            def snapshot(self):return {'halted':self.saved}
            def halt(self,*,reason,context):self.saved={'reason':reason,'context':context}
        ledger=FakeLedger()
        def invalid():raise ResearchError('STUDY_CLOCK_CHANGED','changed boot')
        with self.assertRaises(ResearchError):runner._phase_start(ledger,'generation',invalid)
        self.assertEqual(ledger.saved['context']['phase'],'generation')
        self.assertEqual(ledger.saved['context']['message'],'changed boot')
        old=deepcopy(ledger.saved)
        with self.assertRaises(ResearchError):runner._phase_start(ledger,'generation',invalid)
        self.assertEqual(ledger.saved,old)

    def test_atomic_output_never_overwrites_and_unreviewed_prepare_never_claims(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'file.json'
            self.assertTrue(runner._write_once(path,{'value':1}))
            self.assertFalse(runner._write_once(path,{'value':1}))
            with self.assertRaises(ResearchError):runner._write_once(path,{'value':2})
            (Path(temp)/'.other.json.pending').write_bytes(b'partial')
            with self.assertRaises(ResearchError):runner._write_once(Path(temp)/'other.json',{'value':1})
        with patch.object(runner,'_environment',return_value=({},{})), \
             patch.object(runner,'_review',side_effect=ResearchError('STUDY_NOT_REVIEWED','no review')), \
             patch.object(runner,'_ledger',side_effect=AssertionError('Must not claim')), \
             patch.object(kernel,'jobs_for',side_effect=AssertionError('No generation')):
            with self.assertRaises(ResearchError) as caught:runner.prepare()
            self.assertEqual(caught.exception.code,'STUDY_NOT_REVIEWED')


if __name__=='__main__':unittest.main()
