"""Synthetic source-conversion checks; no public dataset or research execution."""
import importlib.util
import json
from pathlib import Path
import unittest
import tempfile
import hashlib
import random
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('s067_test_driver', ROOT / 'scripts/run_boolq_case_comparison_study.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


class BoolQPreparationTests(unittest.TestCase):
    def rows(self):
        rows = [{'question': f'Unique question {i}', 'title': f'Title {i}',
                 'passage': f'Distinct passage {i}', 'answer': bool(i % 2)} for i in range(6)]
        rows.append({'question': 'Additional unique question', 'title': 'A title',
                     'passage': 'Distinct passage 0', 'answer': True})
        return rows

    def convert(self, rows):
        return driver.derive_source(rows, split_size=2, expected_rows=7, expected_groups=6)

    def test_groups_keep_first_question_all_titles_and_distinct_splits(self):
        result = self.convert(self.rows())
        self.assertEqual(result['document_count'], 6)
        docs = [json.loads(line) for line in result['corpus'].splitlines()]
        group = next(d for d in docs if d['text'] == 'Distinct passage 0')
        self.assertEqual(group['title'], 'A title')
        citation = next(d for d in result['sidecar'] if d['doc_id'] == group['_id'])
        self.assertEqual(citation['titles'], ['A title', 'Title 0'])
        self.assertEqual(citation['revision'], 'unknown')
        selected = sum(result['selection'].values(), [])
        self.assertEqual(len(selected), 6)
        self.assertEqual(len({r['positive_doc_ids'][0] for r in selected}), 6)
        row = next(r for r in selected if r['positive_doc_ids'] == [group['_id']])
        self.assertEqual(row['qid'], 'q-boolq-dev-00000001')
        self.assertEqual(row['text'], 'Unique question 0')
        self.assertTrue(all(r['qid'].startswith('q-') for r in selected))

    def test_duplicate_normalized_questions_and_wrong_group_count_stop(self):
        rows = self.rows()
        rows[-1]['question'] = '  UNIQUE   QUESTION 0  '
        with self.assertRaisesRegex(RuntimeError, 'duplicated'):
            self.convert(rows)
        with self.assertRaisesRegex(RuntimeError, 'group count'):
            driver.derive_source(self.rows(), split_size=2, expected_rows=7, expected_groups=7)

    def test_answer_never_affects_conversion(self):
        rows = self.rows()
        changed = [dict(r, answer={'opaque': 'ignored'}) for r in rows]
        self.assertEqual(self.convert(rows), self.convert(changed))

    def test_strict_jsonl_rejects_duplicates_and_empty_line(self):
        with self.assertRaises(Exception):
            driver.parse_jsonl(b'{"question":"x","question":"y"}\n')
        with self.assertRaises(RuntimeError):
            driver.parse_jsonl(b'{}\n\n{}\n')

    def test_unpublished_or_noncanonical_pin_rejected_before_execution(self):
        with patch.object(driver, 'prepare', side_effect=AssertionError('preparation must not start')) as prepare, \
             patch.object(driver.sys, 'argv', ['driver', '--source-commit', 'not-a-commit', '--prepare']):
            with self.assertRaisesRegex(RuntimeError, 'canonical checkout'):
                driver.main()
        prepare.assert_not_called()

    def test_cli_help_without_published_pin_has_no_study_action(self):
        import subprocess, sys
        result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/run_boolq_case_comparison_study.py'),'--help'],
                              capture_output=True,text=True,cwd=ROOT,check=False)
        self.assertEqual(result.returncode,0)
        self.assertIn('--source-commit',result.stdout)
        self.assertIn('--prepare',result.stdout)
        self.assertIn('--run',result.stdout)
        self.assertIn('--resume',result.stdout)

    def test_wrong_remote_rejected_before_publication_or_source(self):
        import subprocess
        fake_repo=Path('/workspace/development-continuation-20261114/source-pins/aaaaaaa')
        def fake_run(argv, **kwargs):
            commands={('rev-parse','HEAD'):b'a'*40+b'\n',
                      ('status','--porcelain','--untracked-files=no'):b'',
                      ('remote','get-url','origin'):b'https://github.com/other/repository.git\n'}
            key=tuple(argv[1:])
            if key not in commands:raise AssertionError('must not reach publication or source')
            return subprocess.CompletedProcess(argv,0,stdout=commands[key],stderr=b'')
        with patch.object(driver,'REPO',fake_repo), patch.object(driver.subprocess,'run',side_effect=fake_run):
            with self.assertRaisesRegex(RuntimeError,'Origin does not identify'):
                driver.source_pin('a'*40)


class BoolQPolicyTests(unittest.TestCase):
    def test_comparison_truth_table_and_zero(self):
        summary={'baseline':{'recall@5':.4,'recall@10':.6,'recall@20':.8,'mrr@10':.7,'ndcg@10':.7},
                 'selected':{'recall@5':.4,'recall@10':.6,'recall@20':.8,'mrr@10':.6,'ndcg@10':.7}}
        self.assertEqual(driver.compare_rules('tfidf_cosine','bm25',summary)['outcome'],'condition_met')
        self.assertEqual(driver.compare_rules('tfidf_cosine','tfidf_cosine',summary)['outcome'],'unknown')
        self.assertEqual(driver.compare_rules('bm25','bm25',None)['outcome'],'unknown')
        self.assertEqual(driver.compare_rules(None,'bm25',summary)['outcome'],'unknown')
        summary['selected']['mrr@10']=.7
        self.assertEqual(driver.compare_rules('tfidf_cosine','bm25',summary)['outcome'],'condition_not_met')
        with self.assertRaises(RuntimeError):driver.compare_rules('bm25','tfidf_cosine',summary)

    def test_atomic_publication_never_replaces_original_or_partial(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'decision.json';driver.atomic_publish_json(path,{'known':0})
            self.assertEqual(driver.read_json(path),{'known':0})
            before=path.read_bytes()
            with self.assertRaises(RuntimeError):driver.atomic_publish_json(path,{'known':1})
            self.assertEqual(path.read_bytes(),before)
            partial=Path(d)/'.other.json.partial';partial.write_bytes(b'partial')
            with self.assertRaises(RuntimeError):driver.atomic_publish_json(Path(d)/'other.json',{'x':1})
            self.assertEqual(partial.read_bytes(),b'partial')

    def _synthetic_native_lifecycle(self, attack=False, interrupt=None, different=False):
        from autoresearch.research_project import code_identity
        if different:
            rng=random.Random(108);terms=['amber','blue','cyan','denim','ecru','frog','green','horse']
            source_rows=[]
            for i in range(2938):
                passage=(' '.join(w for w in terms for _ in range(rng.randint(0,7)))+' tag'+str(i)) if i<500 else 'uniquepassage'+str(i)
                source_rows.append({'question':f'questionxyz{i}','title':f'Synthetic title {i}','passage':passage,'answer':True})
            source_rows.extend({'question':f'extraquestionxyz{i}','title':f'Second title {i}',
                                'passage':source_rows[i]['passage'],'answer':False} for i in range(332))
            # Fixed, wholly synthetic construction: exactly one validation positive enters TF-IDF top-20 only.
            source_rows[353]['question']='amber cyan ecru'
        else:
            source_rows=[{'question':f'synthetic unique question {i}', 'title':f'Synthetic title {i}',
                          'passage':f'synthetic passage {i} unique tokens', 'answer':True} for i in range(2938)]
            source_rows.extend({'question':f'second question {i}', 'title':f'Second title {i}',
                                'passage':f'synthetic passage {i} unique tokens', 'answer':False} for i in range(332))
        raw=('\n'.join(json.dumps(r,separators=(',',':')) for r in source_rows)+'\n').encode()
        protocol=json.loads((ROOT/'docs/execution/g5-local/boolq-case-comparison-protocol-v1.json').read_bytes())
        identity={'source_commit':'a'*40,'publication':{'method':'synthetic'},'protocol_sha256':driver.PROTOCOL_SHA,
                  'driver_sha256':hashlib.sha256((ROOT/'scripts/run_boolq_case_comparison_study.py').read_bytes()).hexdigest(),
                  'helper_sha256':hashlib.sha256(driver.S046.read_bytes()).hexdigest(),
                  'test_sha256':hashlib.sha256((ROOT/'tests/test_boolq_case_comparison_study.py').read_bytes()).hexdigest(),
                  'project_code_identity':code_identity(),'controller_code_identity':driver.controller_identity(),
                  'runtime_dependencies':driver.method_registry.runtime_dependencies(),'python':'synthetic','unicode':'synthetic'}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'synthetic.jsonl';source.write_bytes(raw)
            with patch.multiple(driver,SOURCE=source,SOURCE_BYTES=len(raw),SOURCE_SHA=hashlib.sha256(raw).hexdigest(),
                                WORKSPACE=root/'study',CLAIM=root/'claims/synthetic.json'), \
                 patch.object(driver,'current_owner',return_value='synthetic-owner'):
                driver.prepare(identity,protocol)
                if attack:
                    from autoresearch.local_workbench import LocalWorkbench
                    original=driver.primary
                    def swap_after_primary(project):
                        result=original(project)
                        path=driver.WORKSPACE/'private/case.canonical.json'
                        case=json.loads(path.read_bytes())
                        case['record']['provenance']['feedback_history']['registration']['condition']['all'][0]['threshold']=123
                        path.write_bytes(driver.encoded(case))
                        return result
                    with patch.object(driver,'primary',side_effect=swap_after_primary):
                        with self.assertRaisesRegex(RuntimeError,'case .*changed'):
                            driver.run(identity,protocol,resume=False)
                    manager=LocalWorkbench.open_readonly(driver.WORKSPACE/'manager')
                    saved=driver.read_json(driver.WORKSPACE/'project-identity.json')
                    with manager._connect(readonly=True) as con:
                        _,project=manager._project(con,saved['project_id'])
                    state=project.status()
                    self.assertEqual(len(state['actions']),1)
                    self.assertEqual(state['budget']['local_tool_calls_used'],1)
                    self.assertFalse(state.get('researcher_feedback'))
                    self.assertFalse((driver.WORKSPACE/'private/shadow-decision.json').exists())
                    self.assertEqual(driver.read_json(driver.WORKSPACE/'stopped.json')['comparison'],
                                     {'outcome':'unknown','reason':'shadow_unavailable','B_minus_A':None})
                    return
                if interrupt=='shadow':
                    original_publish=driver.atomic_publish_json
                    def interrupt_decision(path,value):
                        if path.name=='shadow-decision.json':raise KeyboardInterrupt('synthetic fault')
                        return original_publish(path,value)
                    with patch.object(driver,'atomic_publish_json',side_effect=interrupt_decision):
                        with self.assertRaises(KeyboardInterrupt):driver.run(identity,protocol,resume=False)
                    self.assertTrue((driver.WORKSPACE/'private/shadow-inputs.json').is_file())
                    self.assertFalse((driver.WORKSPACE/'private/shadow-decision.json').exists())
                    with self.assertRaisesRegex(RuntimeError,'shadow records are incomplete'):
                        driver.run(identity,protocol,resume=True)
                    from autoresearch.local_workbench import LocalWorkbench
                    manager=LocalWorkbench.open_readonly(driver.WORKSPACE/'manager')
                    saved=driver.read_json(driver.WORKSPACE/'project-identity.json')
                    with manager._connect(readonly=True) as con:_,project=manager._project(con,saved['project_id'])
                    state=project.status()
                    self.assertEqual(len(state['actions']),1)
                    self.assertFalse(state.get('researcher_feedback'))
                    self.assertEqual(driver.read_json(driver.WORKSPACE/'stopped.json')['comparison']['outcome'],'unknown')
                    return
                if interrupt=='drift':
                    from autoresearch.local_workbench import LocalWorkbench
                    original_shadow=driver.shadow_and_anchor
                    def add_unrelated_feedback(project,action,identity,**kwargs):
                        value=original_shadow(project,action,identity,**kwargs)
                        project.record_feedback(request_id='synthetic-extra-feedback',expected_state_version=project.status()['state_version'],
                                                author='test',comment='synthetic state drift',next_step='',action_id=action['id'])
                        return value
                    with patch.object(driver,'shadow_and_anchor',side_effect=add_unrelated_feedback):
                        with self.assertRaisesRegex(RuntimeError,'state changed after shadow anchor'):
                            driver.run(identity,protocol,resume=False)
                    manager=LocalWorkbench.open_readonly(driver.WORKSPACE/'manager')
                    saved=driver.read_json(driver.WORKSPACE/'project-identity.json')
                    with manager._connect(readonly=True) as con:
                        _,project=manager._project(con,saved['project_id'])
                        row=con.execute('SELECT 1 FROM requests WHERE id=?',(driver.IDS['conditional'],)).fetchone()
                    state=project.status()
                    self.assertIsNone(row);self.assertEqual(len(state['actions']),1)
                    self.assertEqual(state['budget']['local_tool_calls_used'],1)
                    self.assertEqual(driver.read_json(driver.WORKSPACE/'stopped.json')['comparison'],
                                     {'outcome':'unknown','reason':'state_changed','B_minus_A':None})
                    return
                if interrupt=='audit':
                    from autoresearch.local_workbench import LocalWorkbench
                    original_save=LocalWorkbench._save_staged_continuation
                    def interrupt_receipt(manager,record):
                        if record['phase']=='freeze' and record['steps']['audit']['status']=='completed':
                            raise KeyboardInterrupt('synthetic audit receipt interruption')
                        return original_save(manager,record)
                    with patch.object(LocalWorkbench,'_save_staged_continuation',interrupt_receipt):
                        with self.assertRaises(KeyboardInterrupt):driver.run(identity,protocol,resume=False)
                    manager=LocalWorkbench.open_readonly(driver.WORKSPACE/'manager')
                    saved=driver.read_json(driver.WORKSPACE/'project-identity.json')
                    with manager._connect(readonly=True) as con:_,project=manager._project(con,saved['project_id'])
                    before=project.status();self.assertEqual(len(before['actions']),2)
                    old_ids=[a['id'] for a in before['actions']]
                    summary=driver.run(identity,protocol,resume=True)
                    self.assertEqual([a['id'] for a in summary['actions'][:2]],old_ids)
                else:
                    summary=driver.run(identity,protocol,resume=False)
                self.assertEqual(summary['budget']['local_tool_calls_used'],3)
                if different:
                    self.assertEqual(summary['shadow_policy']['native_A_method'],'tfidf_cosine')
                    self.assertEqual(summary['shadow_policy']['method'],'bm25')
                    self.assertEqual(summary['shadow_policy']['value']['leave_one_out']['minimum'],0)
                    self.assertEqual(summary['comparison']['outcome'],'condition_not_met')
                    self.assertEqual(summary['final_usage']['ranking_calls'],400)
                else:
                    self.assertEqual(summary['comparison']['outcome'],'unknown')
                    self.assertEqual(summary['comparison']['reason'],'same_arm')
                self.assertEqual(summary['budget']['new_model_requests'],0)
                self.assertEqual(summary['budget']['new_fits'],0)
                self.assertEqual(summary,driver.terminal_replay(identity,protocol))

    def test_synthetic_native_lifecycle_with_fixed_history(self):
        self._synthetic_native_lifecycle()

    def test_changed_case_between_primary_and_decision_cannot_dispatch(self):
        self._synthetic_native_lifecycle(attack=True)

    def test_partial_shadow_publication_cannot_dispatch(self):
        self._synthetic_native_lifecycle(interrupt='shadow')

    def test_audit_receipt_interruption_resumes_original_action_ids(self):
        self._synthetic_native_lifecycle(interrupt='audit')

    def test_different_rules_measure_both_final_arms(self):
        self._synthetic_native_lifecycle(different=True)

    def test_state_drift_after_anchor_cannot_accept_conditional(self):
        self._synthetic_native_lifecycle(interrupt='drift')


if __name__ == '__main__':
    unittest.main()
