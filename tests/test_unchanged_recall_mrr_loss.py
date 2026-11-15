"""Synthetic-only tests for the S108 retrospective magnitude reader."""
import copy
import importlib.util
import json
import math
import marshal
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result); return result
reader = module('s108_reader', ROOT/'scripts/audit_unchanged_recall_mrr_loss.py')
base = module('s075_reader_for_s108_test', ROOT/'scripts/audit_saved_joint_validation.py')


def fixture(n=5, tiny=False):
    rows=[]
    for i in range(n):
        delta = 2e-12 if tiny else (i+1)/100
        rows.append({'query_id':'synthetic-'+str(i),'baseline':{'recall@20':.5,'mrr@10':.5},
                     'candidate':{'recall@20':.5,'mrr@10':.5-delta}})
    saved={'recall@20':{'mean':0.0,'wins':0,'ties':n,'losses':0},
           'mrr@10':{'mean':sum(r['candidate']['mrr@10']-r['baseline']['mrr@10'] for r in rows)/n,
                     'wins':0,'ties':0,'losses':n}}
    return rows,saved,base.summarize(rows,saved,n)


class UnchangedRecallLossTests(unittest.TestCase):
    def test_exact_cell_magnitude_and_suppression(self):
        rows,saved,prior=fixture()
        result=reader.summarize_cell(base,rows,saved,5,prior)
        self.assertEqual(result,{'status':'available','count':5,'mean_mrr_loss':.03})
        self.assertNotIn('synthetic-',str(result))
        for n in (1,4):
            rows,saved,prior=fixture(n)
            self.assertEqual(reader.summarize_cell(base,rows,saved,n,prior),{'status':'suppressed','count':None,'mean_mrr_loss':None})
        rows,saved,prior=fixture(5,tiny=True)
        self.assertEqual(reader.summarize_cell(base,rows,saved,5,prior)['mean_mrr_loss'],0.0)
        # Empty selected cell while valid coverage remains nonempty.
        rows,saved,prior=fixture(5)
        for row in rows: row['candidate']['mrr@10']=row['baseline']['mrr@10']
        saved['mrr@10']={'mean':0.0,'wins':0,'ties':5,'losses':0}
        prior=base.summarize(rows,saved,5)
        self.assertEqual(reader.summarize_cell(base,rows,saved,5,prior)['status'],'suppressed')

    def test_full_prior_summary_and_type_drift_fail(self):
        rows,saved,prior=fixture()
        for change in ('matrix','mean','boolean','duplicate','missing'):
            r,s,p=copy.deepcopy(rows),copy.deepcopy(saved),copy.deepcopy(prior)
            if change=='matrix': p['matrix'][1][0]+=1
            if change=='mean': s['mrr@10']['mean']+=.1
            if change=='boolean': r[0]['candidate']['mrr@10']=True
            if change=='duplicate': r[0]['query_id']=r[1]['query_id']
            if change=='missing': r.pop()
            with self.subTest(change=change),self.assertRaises((ValueError,KeyError)):
                reader.summarize_cell(base,r,s,5,p)

    def test_recall_epsilon_endpoints_use_raw_mrr_delta(self):
        rows=[]
        for i in range(7):
            baseline=0.0 if i != 1 else 1e-12
            candidate=1e-12 if i == 0 else 0.0 if i == 1 else 2e-12 if i >= 5 else 0.0
            rows.append({'query_id':'synthetic-'+str(i),'baseline':{'recall@20':baseline,'mrr@10':.5},
                         'candidate':{'recall@20':candidate,'mrr@10':.4}})
        saved={}
        for metric in ('recall@20','mrr@10'):
            deltas=[r['candidate'][metric]-r['baseline'][metric] for r in rows]
            categories=[base.category(d) for d in deltas]
            saved[metric]={'mean':math.fsum(deltas)/len(deltas),'wins':categories.count('positive'),
                           'ties':categories.count('zero'),'losses':categories.count('negative')}
        prior=base.summarize(rows,saved,7)
        self.assertEqual(reader.summarize_cell(base,rows,saved,7,prior),
                         {'status':'available','count':5,'mean_mrr_loss':.1})

    def test_prior_identity_and_coverage_fail_closed(self):
        old=json.loads((ROOT/'docs/execution/g5-local/saved-joint-validation-protocol-v1.json').read_text())
        proto=json.loads((ROOT/'docs/execution/g5-local/saved-unchanged-recall-mrr-loss-protocol-v1.json').read_text())
        deps=proto['s075_dependencies']; entries=[]
        for case in old['cases']:
            entries.append({'case':case['label'], **{k:case[k] for k in ('project_id','run_id','producer_core','source_snapshot_sha256','primary_action_id','primary_result_sha256')},'aggregate':{'queries':case['validation_queries']}})
        prior={'schema_version':'saved-joint-validation-audit-v1','protocol_sha256':deps['protocol_sha256'],'script_sha256':deps['script_sha256'],'cases':entries}
        self.assertEqual(set(reader.validate_prior(proto,prior,old)),{100,200})
        for change in ('identity','duplicate','coverage','old_protocol'):
            p,o=copy.deepcopy(prior),copy.deepcopy(old)
            if change=='identity':p['cases'][0]['project_id']='wrong'
            if change=='duplicate':p['cases'][1]['case']=p['cases'][0]['case']
            if change=='coverage':p['cases'][0]['aggregate']['queries']=99
            if change=='old_protocol':o['cases'][0]['source_commit']='f'*40
            with self.subTest(change=change),self.assertRaises(ValueError):reader.validate_prior(proto,p,o)

    def test_guard_blocks_alias_private_artifact_writes_socket_and_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);repo=root/'reader';repo.mkdir(); case=root/'source-pins'/'pin'/'runs'/'case';case.mkdir(parents=True)
            private=case/'private';private.mkdir();(private/'secret').write_text('synthetic')
            alias=root/'alias';alias.symlink_to(private, target_is_directory=True)
            artifact=case/'artifacts';artifact.mkdir();(artifact/'other.json').write_text('{}')
            proto={'cases':[{'workspace':'pin/runs/case','primary_action_id':'allowed'}]}
            paths=[lambda:alias.joinpath('secret').read_text(),lambda:(artifact/'other.json').read_text(),
                   lambda:(case/'write').write_text('no'),lambda:reader.socket.socket(),lambda:reader.subprocess.Popen(['true'])]
            for action in paths:
                fake=SimpleNamespace(summarize=lambda *a:None,verify_finish=lambda *a:None,perform=lambda *a:action())
                with self.subTest(action=action),patch.object(reader,'check_source_tree'),self.assertRaises(AssertionError):
                    reader.run_guarded(fake,repo,proto,{},SimpleNamespace(),{}, {})
            self.assertFalse((case/'write').exists())

    def test_guarded_wrapper_returns_only_the_requested_cell(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);repo=root/'reader';repo.mkdir();case=root/'source-pins'/'pin'/'runs'/'case';case.mkdir(parents=True)
            rows,saved,aggregate=fixture()
            fixed={'case':'SYN','project_id':'project','run_id':'run','producer_core':'core',
                   'source_snapshot_sha256':'source','primary_action_id':'action','primary_result_sha256':'result',
                   'primary_artifact_sha256':'artifact','aggregate':aggregate}
            proto={'cases':[{'label':'SYN','workspace':'pin/runs/case','primary_action_id':'action',
                             'validation_queries':5,'source_commit':'c'*40}], 's075_dependencies':{'script':'fixed-s075.py'}}
            fake=SimpleNamespace(summarize=base.summarize,verify_finish=lambda *a:None)
            def perform(*args):
                cell=fake.summarize(rows,saved,5);fake.verify_finish()
                return {'cases':[{k:v for k,v in fixed.items() if k!='aggregate'}|{'aggregate':cell}]}
            fake.perform=perform
            with patch.object(reader,'check_source_tree'):
                _,output=reader.run_guarded(fake,repo,proto,{},SimpleNamespace(),{5:fixed},{})
            self.assertEqual(output[0]['cell'],{'status':'available','count':5,'mean_mrr_loss':.03})
            self.assertNotIn('synthetic-',str(output));self.assertNotIn('matrix',str(output))
            self.assertEqual(output[0]['source_commit'],'c'*40)

    def test_each_dependency_drift_after_summary_stops_before_result(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);repo=root/'reader';source=repo/'src/autoresearch/__init__.py';source.parent.mkdir(parents=True);source.write_text('source')
            paths=[repo/'wrapper.py',repo/'old.py',repo/'old-protocol.json',repo/'old-result.json',repo/'new-protocol.json',repo/'test.py']
            for path in paths:path.write_text('fixed-'+path.name)
            manifest={str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [source,*paths]}
            case=root/'source-pins'/'pin'/'runs'/'case';case.mkdir(parents=True)
            rows,saved,aggregate=fixture();prior={5:{'aggregate':aggregate}}
            protocol={'cases':[{'workspace':'pin/runs/case','primary_action_id':'action'}],
                      's075_dependencies':{'script':'old.py'}}
            for changed in paths:
                fake=SimpleNamespace(__file__=str(paths[1]),summarize=base.summarize,verify_finish=lambda *a:None)
                def perform(*args):
                    fake.summarize(rows,saved,5);changed.write_text('changed');fake.verify_finish()
                fake.perform=perform
                with self.subTest(changed=changed.name),patch.object(reader,'check_modules'),self.assertRaises(ValueError):
                    reader.run_guarded(fake,repo,protocol,{},SimpleNamespace(),prior,manifest)
                changed.write_text('fixed-'+changed.name)
            fake.__file__=str(paths[0])
            with patch.object(reader,'check_modules'),self.assertRaises(ValueError):
                reader.check_source_tree(repo,manifest,fake,paths[1])

    def test_import_path_outside_pin_is_rejected(self):
        fake=SimpleNamespace(__file__='/tmp/not-the-published-source.py')
        with tempfile.TemporaryDirectory() as temporary:
            repo=Path(temporary);(repo/'src/autoresearch').mkdir(parents=True)
            outside=Path(fake.__file__)
            # Existing temporary module file is outside the pinned package.
            external=repo/'outside.py';external.write_text('synthetic');fake.__file__=str(external)
            with patch.dict(sys.modules,{'autoresearch.synthetic_for_s108':fake}),self.assertRaises(ValueError):
                reader.check_modules(repo,{})

    def test_verified_source_loader_ignores_valid_but_forged_pyc(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'synthetic_s075.py';source.write_text("VALUE='source'\n")
            cache=Path(py_compile.compile(str(source),doraise=True));header=cache.read_bytes()[:16]
            code=compile("VALUE='forged'\n",str(source),'exec');forged=header+marshal.dumps(code);cache.write_bytes(forged)
            result=subprocess.run([sys.executable,'-B','-c',f"import sys;sys.path.insert(0,{str(root)!r});import synthetic_s075;print(synthetic_s075.VALUE)"],
                                  capture_output=True,text=True,check=True)
            self.assertEqual(result.stdout.strip(),'forged')
            module=reader.load_s075_source(source,hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(module.VALUE,'source');self.assertEqual(cache.read_bytes(),forged)
            with self.assertRaises(ValueError):reader.load_s075_source(source,'0'*64)

    def test_output_rejects_links_overlap_and_directory_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);repo=root/'reader';allowed=repo/'runs/s108-verification';allowed.mkdir(parents=True)
            original=root/'source-pins'/'pin'/'runs'/'case';original.mkdir(parents=True)
            cases=[{'workspace':'pin/runs/case'}];target=allowed/'result.json'
            selected,identity=reader.validate_output_target(repo,target,cases)
            reader.verify_output_target(repo,target,cases,selected,identity)
            (allowed/'nested-link').symlink_to(original,target_is_directory=True)
            with self.assertRaises(ValueError):reader.validate_output_target(repo,allowed/'nested-link'/'result.json',cases)
            (allowed/'nested-link').unlink()
            moved=repo/'runs/original-output';allowed.rename(moved);allowed.symlink_to(original,target_is_directory=True)
            with self.assertRaises(ValueError):reader.validate_output_target(repo,target,cases)
            allowed.unlink();allowed.mkdir()
            with self.assertRaises(ValueError):reader.verify_output_target(repo,target,cases,selected,identity)
            overlap=[{'workspace':'../reader/runs/s108-verification/inside-case'}]
            with self.assertRaises(ValueError):reader.validate_output_target(repo,target,overlap)
            self.assertFalse((original/'result.json').exists())

    def test_default_is_dry_and_errors_are_sanitized(self):
        path=ROOT/'scripts/audit_unchanged_recall_mrr_loss.py'
        result=subprocess.run([sys.executable,'-B',str(path)],capture_output=True,text=True,check=True)
        self.assertIn('draft_only_no_analysis',result.stdout)
        result=subprocess.run([sys.executable,'-B',str(path),'--execute'],capture_output=True,text=True)
        self.assertEqual(result.returncode,1);self.assertNotIn('Traceback',result.stderr)
        self.assertNotIn('synthetic-',result.stderr)

    def test_directory_fsync_failure_keeps_complete_unconfirmed_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)/'result.json'; real=os.fsync; calls=[]
            def sync(fd):
                calls.append(fd)
                if len(calls)==2: raise OSError('synthetic directory fsync failure')
                return real(fd)
            with patch.object(base.os,'fsync',side_effect=sync),self.assertRaises(OSError):
                base.publish_new(target,{'synthetic':'complete'})
            self.assertEqual(json.loads(target.read_text()),{'synthetic':'complete'})
            with self.assertRaises(FileExistsError):base.publish_new(target,{'overwrite':True})
            self.assertEqual(json.loads(target.read_text()),{'synthetic':'complete'})

    def test_published_checks_all_source_and_new_dependency_blobs(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo=Path(temporary);source=repo/'src/autoresearch/__init__.py';source.parent.mkdir(parents=True);source.write_text('source')
            wrapper=repo/'audit.py';wrapper.write_text('audit'); commit='a'*40; tree='src/autoresearch/__init__.py\n'
            blobs={'src/autoresearch/__init__.py':b'source','audit.py':b'audit'}
            def output(command,text=True):
                args=command[3:]
                if args==['rev-parse','HEAD']:value=commit+'\n'
                elif args==['remote','get-url','origin']:value='https://github.com/open-agent-power/auto-research-agentarts.git\n'
                elif args==['ls-remote','origin','refs/heads/main']:value='b'*40+'\trefs/heads/main\n'
                elif args[0]=='status':value=''
                elif args[0]=='ls-tree':value=tree
                elif args[0]=='show':return blobs[args[1].split(':',1)[1]]
                else:raise AssertionError(args)
                return value if text else value.encode()
            with patch.object(reader.subprocess,'check_output',side_effect=output),patch.object(reader.subprocess,'check_call'):
                _,manifest=reader.published(repo,commit,[wrapper]);self.assertEqual(set(manifest),{'src/autoresearch/__init__.py','audit.py'})
                wrapper.write_text('modified')
                with self.assertRaises(ValueError):reader.published(repo,commit,[wrapper])
                wrapper.write_text('audit');(source.parent/'shadow.py').write_text('untracked')
                with self.assertRaises(ValueError):reader.published(repo,commit,[wrapper])

if __name__=='__main__':unittest.main()
