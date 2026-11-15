"""Pure synthetic joint-accounting checks; never open study inputs."""
import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'scripts/audit_saved_joint_validation.py'
spec = importlib.util.spec_from_file_location('joint_validation', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class JointValidationTests(unittest.TestCase):
    def test_joint_counts_margins_and_zero_are_distinct(self):
        rows = [
            {'query_id':'q1','baseline':{'recall@20':.5,'mrr@10':.5},'candidate':{'recall@20':.7,'mrr@10':.4}},
            {'query_id':'q2','baseline':{'recall@20':.5,'mrr@10':.5},'candidate':{'recall@20':.5,'mrr@10':.5}},
            {'query_id':'q3','baseline':{'recall@20':.5,'mrr@10':.5},'candidate':{'recall@20':.4,'mrr@10':.7}},
        ]
        saved={'recall@20':{'mean':.1/3,'wins':1,'ties':1,'losses':1},
               'mrr@10':{'mean':.1/3,'wins':1,'ties':1,'losses':1}}
        result=module.summarize(rows,saved,3)
        self.assertEqual(result['matrix'],[[0,0,1],[0,1,0],[1,0,0]])
        self.assertEqual(module.category(1e-12),'zero');self.assertEqual(module.category(-1e-12),'zero')
        self.assertEqual(module.category(1.1e-12),'positive');self.assertEqual(module.category(-1.1e-12),'negative')
        self.assertNotIn('q1',str(result))
        for mutation in ('duplicate','boolean','summary','missing'):
            broken, altered = copy.deepcopy(rows),copy.deepcopy(saved)
            if mutation == 'duplicate':broken[0]['query_id']=broken[1]['query_id']
            if mutation == 'boolean':broken[0]['candidate']['mrr@10']=True
            if mutation == 'summary':altered['mrr@10']['wins']=2
            if mutation == 'missing':broken.pop()
            with self.subTest(mutation=mutation),self.assertRaises((ValueError,KeyError)):
                module.summarize(broken,altered,3)

    def test_default_mode_does_not_open_study_cases(self):
        result=subprocess.run([sys.executable,'-B',str(PATH)],text=True,capture_output=True,check=True)
        self.assertIn('draft_only_no_analysis',result.stdout)

    def test_producer_pin_requires_exact_head_canonical_origin_and_clean_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);repo=root/'reader';repo.mkdir()
            pin=root/'source-pins'/'pin1';pin.mkdir(parents=True)
            protocol={'cases':[{'workspace':'pin1/runs/case','source_commit':'a'*40}]}
            for change in ('valid','head','origin','dirty'):
                def output(command, text):
                    action=command[3:]
                    if action==['rev-parse','HEAD']:return ('b' if change=='head' else 'a')*40
                    if action==['remote','get-url','origin']:
                        return 'https://example.invalid/fork' if change=='origin' else 'https://github.com/open-agent-power/auto-research-agentarts.git'
                    if action[0]=='status':return '?? src/autoresearch/shadow.py' if change=='dirty' else ''
                    raise AssertionError(action)
                with self.subTest(change=change), patch.object(module.subprocess,'check_output',side_effect=output), patch.object(module.subprocess,'check_call') as ancestry:
                    if change=='valid':
                        module.producer_pins(repo,protocol,'c'*40);ancestry.assert_called_once()
                    else:
                        with self.assertRaises(ValueError):module.producer_pins(repo,protocol,'c'*40)
                        ancestry.assert_not_called()

    def test_finish_rejects_changes_after_checked_primary(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)/'reader.py';source.write_text('fixed')
            sha=hashlib.sha256(source.read_bytes()).hexdigest()
            state={'snapshot_ref':'snapshot'};action={'id':'action'}
            values={'source':'source-sha','artifact':'artifact-sha','core':'core','state':state}
            evidence=SimpleNamespace(_dev_source=lambda p,s:(values['source'],None,None),
                _read=lambda p,a:(None,values['artifact']),_verify_action_rows=lambda p,a:None)
            reader=SimpleNamespace(__file__=str(source),evidence=evidence)
            project=SimpleNamespace(status=lambda:values['state'])
            checked={'source_sha':'source-sha','artifact_sha':'artifact-sha'}
            def verify():module.verify_finish(reader,project,state,action,checked,sha,'core',lambda:values['core'])
            verify()
            for key in ('source','artifact','core','state','reader'):
                old=values.get(key)
                if key=='reader':source.write_text('changed')
                else:values[key]={'snapshot_ref':'changed'} if key=='state' else 'changed'
                with self.subTest(change=key),self.assertRaises(ValueError):verify()
                if key=='reader':source.write_text('fixed')
                else:values[key]=old

    def test_atomic_publish_preserves_prior_or_absent_target_on_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);target=root/'result.json'
            def partial_dump(value, stream, **kwargs):
                stream.write('{"partial":');raise OSError('synthetic disk failure')
            with patch.object(module.json,'dump',side_effect=partial_dump),self.assertRaises(OSError):
                module.publish_new(target,{'ok':True})
            self.assertFalse(target.exists());self.assertEqual(list(root.iterdir()),[])
            with patch.object(module.os,'fsync',side_effect=OSError('synthetic fsync failure')),self.assertRaises(OSError):
                module.publish_new(target,{'ok':True})
            self.assertFalse(target.exists());self.assertEqual(list(root.iterdir()),[])
            target.write_text('prior complete bytes')
            with self.assertRaises(FileExistsError):module.publish_new(target,{'ok':True})
            self.assertEqual(target.read_text(),'prior complete bytes');self.assertEqual(list(root.iterdir()),[target])
            target.unlink();module.publish_new(target,{'ok':True})
            self.assertEqual(target.read_text(),'{\n  "ok": true\n}\n');self.assertEqual(list(root.iterdir()),[target])


if __name__ == '__main__': unittest.main()
