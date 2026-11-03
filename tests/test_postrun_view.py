import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from autoresearch.postrun_view import _assessment, allowed_iteration_snapshots, read_postrun_artifacts
from autoresearch.contracts import ResearchError, canonical, fingerprint


class PostrunViewTests(unittest.TestCase):
    def test_current_or_explicit_history_binding_preserves_postrun_original_identity(self):
        current={'snapshot_sha256':'a'*64,'prior_evidence':{'known_iterations':[{'snapshot_sha256':'b'*64},{'snapshot_sha256':'b'*64}]}}
        self.assertEqual(allowed_iteration_snapshots(current),{'a'*64,'b'*64})
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            def save(binding):
                view={'schema_version':'p02-postrun-view-v1','iteration_snapshot_sha256':binding,'scientific_validation':False}
                view['snapshot_sha256']=fingerprint(view);raw=(canonical(view)+'\n').encode()
                manifest={'schema_version':'p02-postrun-artifacts-v1','snapshot_sha256':view['snapshot_sha256'],
                          'iteration_snapshot_sha256':binding,'files':{'postrun.json':{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}}}
                (root/'postrun.json').write_bytes(raw);(root/'manifest.json').write_text(canonical(manifest),encoding='utf-8')
                return raw
            for binding in ('a'*64,'b'*64):
                raw=save(binding);self.assertEqual(read_postrun_artifacts(root,current)['postrun.json'],raw)
            save('c'*64)
            with self.assertRaises(ResearchError):read_postrun_artifacts(root,current)
            with self.assertRaises(ResearchError):allowed_iteration_snapshots({'snapshot_sha256':'a'*64,'prior_evidence':{'known_iterations':[{'snapshot_sha256':'not-a-hash'}]}})

    def test_assessment_cannot_promote_approval_or_attach_to_another_proposal(self):
        state = {'actions': [{'id': 'p1', 'action': 'propose_next'}]}; source = {'snapshot_sha256': 'a' * 64}
        note = {'schema_version': 'postrun-assessment-v1', 'source_snapshot_sha256': 'a' * 64,
                'proposal_action_id': 'p1', 'status': 'needs_revision', 'origin': 'operator_assistant_inspection',
                'notes': ['A known experiment was proposed again.']}
        self.assertEqual(_assessment(note, state, source), note)
        for change in ({'status': 'approved'}, {'proposal_action_id': 'p2'}, {'origin': 'scientific_reviewer'}):
            with self.assertRaises(ResearchError):
                _assessment({**note, **change}, state, source)

    def test_exact_artifact_identity_and_iteration_binding(self):
        iteration = {'snapshot_sha256': 'b' * 64}
        view = {'schema_version': 'p02-postrun-view-v1', 'iteration_snapshot_sha256': iteration['snapshot_sha256'],
                'scientific_validation': False, 'controller_reason': 'REQUEST_LIMIT'}
        view['snapshot_sha256'] = fingerprint(view); raw = (canonical(view) + '\n').encode('utf-8')
        manifest = {'schema_version': 'p02-postrun-artifacts-v1', 'snapshot_sha256': view['snapshot_sha256'],
                    'iteration_snapshot_sha256': iteration['snapshot_sha256'],
                    'files': {'postrun.json': {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}}}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'postrun.json').write_bytes(raw)
            (root / 'manifest.json').write_text(canonical(manifest), encoding='utf-8')
            self.assertEqual(read_postrun_artifacts(root, iteration)['postrun.json'], raw)
            with self.assertRaises(ResearchError):
                read_postrun_artifacts(root, {'snapshot_sha256': 'c' * 64})
            changed = copy.deepcopy(view); changed['controller_reason'] = 'MODEL_STOPPED'
            (root / 'postrun.json').write_text(canonical(changed), encoding='utf-8')
            with self.assertRaises(ResearchError):
                read_postrun_artifacts(root, iteration)


if __name__ == '__main__':
    unittest.main()
