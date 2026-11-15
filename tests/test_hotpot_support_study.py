"""Synthetic-only S065 source, durable native branch and recovery checks."""
from contextlib import ExitStack
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from autoresearch import retrieval_holdout, staged_relevance_adapter as staged, project_report
from autoresearch.contracts import ResearchError, canonical
from autoresearch.local_workbench import LocalWorkbench
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import code_identity

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/run_hotpot_support_study.py'
spec=importlib.util.spec_from_file_location('s065_driver_test',SCRIPT)
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)


def rows(mode='notmet'):
    ids=['id%05d'%n for n in range(7405)]
    chosen=set(sorted(ids,key=lambda x:(hashlib.sha256((driver.SEED+x).encode()).hexdigest(),x.encode()))[:300])
    randomizer=random.Random(108);words=['amber','blue','cyan','denim','ecru']
    common=[['Title '+str(i),[' '.join(w for w in words for _ in range(randomizer.randint(0,5)))]] for i in range(40)]
    values=[]
    for qid in ids:
        if mode=='met' and qid in chosen:
            question='amber blue cyan unique'+qid;context=copy.deepcopy(common);support=[['Title 21',0]]
        else:
            question='unique'+qid;context=[['Title '+qid,['unique'+qid+' passage']]];support=[['Title '+qid,0]]
        values.append({'_id':qid,'question':question,'context':context,'supporting_facts':support,'answer':'NOT_USED'})
    return values


class HotpotDriverTests(unittest.TestCase):
    def setup_driver(self,mode='notmet'):
        root=Path(self.enterContext(tempfile.TemporaryDirectory()));source=root/'synthetic-input.json'
        raw=json.dumps(rows(mode),ensure_ascii=False,separators=(',',':')).encode();source.write_bytes(raw)
        patches=ExitStack();self.addCleanup(patches.close)
        patches.enter_context(patch.multiple(driver,SOURCE=source,SOURCE_BYTES=len(raw),SOURCE_SHA=hashlib.sha256(raw).hexdigest(),
            WORKSPACE=root/'study',CLAIM=root/'claims'/('synthetic-'+mode+'.json')))
        patches.enter_context(patch.object(driver,'current_owner',return_value='synthetic-test-owner'))
        protocol=json.loads((SCRIPT.parents[1]/'docs/execution/g5-local/hotpot-support-protocol-v1.json').read_text())
        protocol['source']['mirror_url']='urn:synthetic';protocol['source']['author_expected_metadata']='urn:synthetic-source'
        protocol['license']['dataset']='synthetic only';protocol['license']['dataset_author_readme']='urn:synthetic-license'
        identity={'source_commit':'a'*40,'publication':{'method':'synthetic'},'protocol_sha256':driver.PROTOCOL_SHA,
                  'driver_sha256':hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
                  'helper_sha256':hashlib.sha256(driver.S046.read_bytes()).hexdigest(),
                  'project_code_identity':code_identity(),'controller_code_identity':driver.controller_identity(),
                  'runtime_dependencies':driver.method_registry.runtime_dependencies(),'python':'synthetic','unicode':'synthetic'}
        return root,identity,protocol

    def test_structural_grouping_id_isolation_and_global_title_conflict(self):
        sample=rows()[:6];result=driver.derive_source(sample,split_size=2,expected_rows=6)
        all_rows=sum(result['selection'].values(),[]);self.assertEqual(len(all_rows),6)
        self.assertTrue(all(r['qid'].startswith('q-') and all(d.startswith('d-') for d in r['positive_doc_ids']) for r in all_rows))
        final={r['qid'] for r in result['selection']['final']}
        public={json.loads(line)['_id'] for line in result['queries'].decode().splitlines()}
        self.assertFalse(final & public)
        duplicate=copy.deepcopy(sample[0]);duplicate['_id']='a';duplicate['question']='  '+duplicate['question'].upper()+'  '
        regrouped=driver.derive_source(sample+[duplicate],split_size=2,expected_rows=7)
        selected={r['qid'] for r in sum(regrouped['selection'].values(),[])}
        self.assertIn('q-a',selected);self.assertNotIn('q-'+sample[0]['_id'],selected)
        bad=copy.deepcopy(sample);bad[1]['context'][0][0]=bad[0]['context'][0][0]
        with self.assertRaisesRegex(RuntimeError,'different sentence'):driver.derive_source(bad,split_size=2,expected_rows=6)
        bad=copy.deepcopy(sample);bad[0]['supporting_facts'][0][1]=True
        with self.assertRaisesRegex(RuntimeError,'coordinate'):driver.derive_source(bad,split_size=2,expected_rows=6)

    def test_preparation_rejects_rehashed_changed_private_question_and_sidecar(self):
        for change in ('question','sidecar'):
            with self.subTest(change=change):
                root,identity,protocol=self.setup_driver();driver.prepare(identity,protocol)
                self.assertFalse((driver.WORKSPACE/'manager').exists())
                prepared=driver.read_json(driver.WORKSPACE/'prepared.json')
                if change=='question':
                    path=driver.WORKSPACE/'private/holdout.json';holdout=driver.read_json(path)
                    lines=holdout['queries_jsonl'].splitlines();q=json.loads(lines[0]);q['text']='Changed source question'
                    lines[0]=canonical(q);holdout['queries_jsonl']='\n'.join(lines)+'\n';path.write_bytes(driver.encoded(holdout))
                    names=['private/holdout.json']
                else:
                    path=driver.WORKSPACE/'private/document-attribution.json';sidecar=driver.read_json(path)
                    sidecar['documents'][0]['title']='Changed title';path.write_bytes(driver.encoded(sidecar))
                    receipt_path=driver.WORKSPACE/'private/source-receipt.json';receipt=driver.read_json(receipt_path)
                    receipt['document_attribution_sha256']=driver.sha(path.read_bytes());receipt_path.write_bytes(driver.encoded(receipt))
                    spec_path=driver.WORKSPACE/'development/spec.json';specification=driver.read_json(spec_path)
                    specification['source_provenance']['source_receipt_sha256']=driver.sha(receipt_path.read_bytes())
                    spec_path.write_bytes(driver.encoded(specification));packet=staged.capture_source(driver.WORKSPACE/'development')
                    source_path=driver.WORKSPACE/'development/source.json';source_path.write_bytes(driver.encoded(packet))
                    prepared['source_snapshot_sha256']=packet['snapshot_sha256']
                    names=['private/document-attribution.json','private/source-receipt.json','development/spec.json','development/source.json']
                for name in names:
                    raw=(driver.WORKSPACE/name).read_bytes();prepared['files'][name]={'bytes':len(raw),'sha256':driver.sha(raw)}
                (driver.WORKSPACE/'prepared.json').write_bytes(driver.encoded(prepared))
                with self.assertRaises(RuntimeError):driver.verify_prepared(identity,protocol)
                self.assertFalse((driver.WORKSPACE/'manager').exists())

    def test_native_known_branches_and_terminal_replay_without_extra_action(self):
        for mode in ('notmet','met'):
            with self.subTest(mode=mode):
                root,identity,protocol=self.setup_driver(mode);driver.prepare(identity,protocol)
                summary=driver.run(identity,protocol,resume=False)
                expected='condition_met' if mode=='met' else 'condition_not_met'
                self.assertEqual(summary['feedback']['outcome'],expected)
                self.assertEqual(summary['selected_method'],'tfidf_cosine' if mode=='met' else 'bm25')
                self.assertEqual(summary['final_status'],'measured');self.assertEqual(summary['budget']['local_tool_calls_used'],3)
                self.assertEqual((summary['budget']['new_model_requests'],summary['budget']['new_fits']),(0,0))
                self.assertEqual(summary['development_usage'],{'tokens':'unknown','cost':'unknown'})
                n=summary['final_query_count'];self.assertEqual(n,100)
                self.assertEqual(summary['final_usage']['ranking_calls'],n if mode=='notmet' else 2*n)
                self.assertEqual(summary['final_usage']['scoring_calls'],n if mode=='notmet' else 2*n)
                self.assertTrue(any('one public data-viewer row' in text for text in summary['limitations']))
                self.assertTrue(any('including eventual final questions and labels' in text for text in summary['limitations']))
                if mode=='notmet':self.assertEqual(summary['final_summary']['delta']['recall@20'],0)
                selection=driver.read_json(driver.WORKSPACE/'private/selection.json')
                self.assertNotIn(selection['final'][0]['qid'],canonical(summary))
                manager=LocalWorkbench.open_readonly(driver.WORKSPACE/'manager')
                with manager._connect(readonly=True) as con:_,project=manager._project(con,summary['project_id'])
                before=project.status()
                with patch.object(ProjectController,'advance_selection',side_effect=AssertionError('no new dispatch')):
                    with patch.object(driver.time,'time',return_value=20000000000):
                        replay=driver.terminal_replay(identity,protocol)
                self.assertEqual(replay,summary);self.assertEqual(project.status(),before)
                if mode=='notmet':
                    writable=LocalWorkbench(driver.WORKSPACE/'manager')
                    with writable._connect() as con:
                        con.execute('UPDATE requests SET digest=? WHERE id=?',('f'*64,driver.IDS['holdout']))
                    with self.assertRaisesRegex(RuntimeError,'manager intent'):
                        driver.plan_cap_holdout(project,writable)
                    self.assertEqual(project.status(),before)

    def test_missing_manager_schema_rejected_without_writes(self):
        root,_,_=self.setup_driver();manager=root/'empty-manager';manager.mkdir();db=manager/'workbench.sqlite';db.write_bytes(b'')
        before=db.read_bytes()
        with self.assertRaises((RuntimeError,ResearchError)):
            driver.verify_resume_manager(manager,root/'seed',{'project_id':'x'})
        self.assertEqual(db.read_bytes(),before)

    def test_interrupted_original_primary_stays_unknown_and_is_not_redispatched(self):
        root,identity,protocol=self.setup_driver();driver.prepare(identity,protocol)
        with patch.object(ProjectController,'_dispatch',side_effect=KeyboardInterrupt('synthetic fault before dispatch')):
            with self.assertRaises(KeyboardInterrupt):driver.run(identity,protocol,resume=False)
        manager=LocalWorkbench.open_readonly(driver.WORKSPACE/'manager')
        saved=driver.read_json(driver.WORKSPACE/'project-identity.json')
        with manager._connect(readonly=True) as con:_,project=manager._project(con,saved['project_id'])
        before=project.status()
        self.assertTrue(any(p['status'] in ('prepared','running','unknown') for p in before['controller_requests']))
        with patch.object(ProjectController,'_dispatch',side_effect=AssertionError('must not redispatch')):
            with self.assertRaisesRegex(RuntimeError,'unfinished|unknown'):driver.run(identity,protocol,resume=True)
        self.assertEqual(project.status(),before)

    def test_existing_claim_or_workspace_never_parses_or_replaces_source(self):
        root,identity,protocol=self.setup_driver();driver.CLAIM.parent.mkdir(parents=True)
        driver.CLAIM.write_bytes(b'original claim');before=driver.CLAIM.read_bytes()
        with patch.object(driver,'derive_source',side_effect=AssertionError('must not parse')):
            with self.assertRaises(FileExistsError):driver.prepare(identity,protocol)
        self.assertEqual(driver.CLAIM.read_bytes(),before);self.assertFalse(driver.WORKSPACE.exists())

    def test_holdout_receipt_interruption_replays_same_body_before_primary(self):
        root,identity,protocol=self.setup_driver();driver.prepare(identity,protocol)
        original=LocalWorkbench._save
        def interrupt_receipt(con,request_id,record):
            if request_id==driver.IDS['holdout'] and record.get('status')=='completed':
                raise KeyboardInterrupt('synthetic holdout receipt interruption')
            return original(con,request_id,record)
        with patch.object(LocalWorkbench,'_save',side_effect=interrupt_receipt):
            with self.assertRaises(KeyboardInterrupt):driver.run(identity,protocol,resume=False)
        manager=LocalWorkbench.open_readonly(driver.WORKSPACE/'manager');identity_saved=driver.read_json(driver.WORKSPACE/'project-identity.json')
        with manager._connect(readonly=True) as con:
            _,project=manager._project(con,identity_saved['project_id'])
            row=con.execute('SELECT record FROM requests WHERE id=?',(driver.IDS['holdout'],)).fetchone()
            self.assertEqual(json.loads(row['record'])['status'],'preparing')
        self.assertIn('private_evaluation',project.status());self.assertEqual(project.status()['actions'],[])
        summary=driver.run(identity,protocol,resume=True)
        self.assertEqual(summary['feedback']['outcome'],'condition_not_met')
        self.assertEqual(summary['budget']['local_tool_calls_used'],3)

    def test_interrupted_after_audit_resumes_original_conditional_without_duplicate(self):
        root,identity,protocol=self.setup_driver();driver.prepare(identity,protocol)
        original=LocalWorkbench._save_staged_continuation
        def interrupt(manager,record):
            if record['phase']=='freeze' and record['steps']['audit']['status']=='completed':
                raise KeyboardInterrupt('synthetic interruption after audit')
            return original(manager,record)
        with patch.object(LocalWorkbench,'_save_staged_continuation',interrupt):
            with self.assertRaises(KeyboardInterrupt):driver.run(identity,protocol,resume=False)
        manager=LocalWorkbench.open_readonly(driver.WORKSPACE/'manager');saved=driver.read_json(driver.WORKSPACE/'project-identity.json')
        with manager._connect(readonly=True) as con:_,project=manager._project(con,saved['project_id'])
        before=project.status();self.assertEqual(len(before['actions']),2)
        original_ids=[a['id'] for a in before['actions']]
        summary=driver.run(identity,protocol,resume=True)
        self.assertEqual([a['id'] for a in summary['actions'][:2]],original_ids)
        self.assertEqual(summary['budget']['local_tool_calls_used'],3)

    def test_report_published_before_interruption_recovers_without_rerender(self):
        root,identity,protocol=self.setup_driver();driver.prepare(identity,protocol)
        original=project_report.export_report
        def after_publish(*args,**kwargs):
            original(*args,**kwargs)
            raise KeyboardInterrupt('synthetic interruption after report publication')
        with patch.object(project_report,'export_report',side_effect=after_publish):
            with self.assertRaises(KeyboardInterrupt):driver.run(identity,protocol,resume=False)
        manager=LocalWorkbench.open_readonly(driver.WORKSPACE/'manager');saved=driver.read_json(driver.WORKSPACE/'project-identity.json')
        with manager._connect(readonly=True) as con:_,project=manager._project(con,saved['project_id'])
        before=project.status();self.assertEqual(before['budget']['local_tool_calls_used'],3)
        with patch.object(project_report,'export_report',side_effect=AssertionError('must not rerender')):
            summary=driver.run(identity,protocol,resume=True)
        self.assertEqual(project.status(),before)
        self.assertEqual(summary['budget']['local_tool_calls_used'],3)

    def test_interrupted_final_is_not_redispatched(self):
        root,identity,protocol=self.setup_driver();driver.prepare(identity,protocol)
        with patch.object(retrieval_holdout.FinalRetrievalEvaluation,'execute_project',side_effect=KeyboardInterrupt('synthetic final interruption')):
            with self.assertRaises(KeyboardInterrupt):driver.run(identity,protocol,resume=False)
        manager=LocalWorkbench.open_readonly(driver.WORKSPACE/'manager');saved=driver.read_json(driver.WORKSPACE/'project-identity.json')
        with manager._connect(readonly=True) as con:_,project=manager._project(con,saved['project_id'])
        before=project.status();self.assertEqual(len(before['actions']),3)
        self.assertNotEqual(before['actions'][-1]['status'],'completed')
        with patch.object(retrieval_holdout.FinalRetrievalEvaluation,'execute_project',side_effect=AssertionError('must not redispatch')):
            with self.assertRaisesRegex(RuntimeError,'unfinished|unknown'):driver.run(identity,protocol,resume=True)
        self.assertEqual(project.status(),before)

    def test_wrong_origin_is_rejected_before_publication_or_claim(self):
        root,_,_=self.setup_driver();commit='a'*40
        def fake_git(args,**kwargs):
            command=args[1:]
            output=(commit+'\n').encode() if command==['rev-parse','HEAD'] else b'' if command==['status','--porcelain','--untracked-files=no'] else b'https://github.com/other/fork.git\n'
            return subprocess.CompletedProcess(args,0,output,b'')
        canonical_pin=Path('/workspace/development-continuation-20261114/source-pins')/commit[:7]
        with patch.object(driver,'REPO',canonical_pin),patch.object(driver.subprocess,'run',side_effect=fake_git) as called:
            with self.assertRaisesRegex(RuntimeError,'designated GitHub'):driver.source_pin(commit)
        self.assertEqual(called.call_count,3);self.assertFalse(driver.CLAIM.exists())
        self.assertFalse(driver.WORKSPACE.exists())
