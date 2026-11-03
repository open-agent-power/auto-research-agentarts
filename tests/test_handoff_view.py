import copy
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from autoresearch import evidence_handoff as handoff, handoff_view as view
from autoresearch.contracts import ResearchError, canonical, fingerprint
from test_evidence_handoff import CATALOG, FACTS, TASK, read_facts, response


class HandoffViewTests(unittest.TestCase):
    def test_exact_native_catalog_binding_selected_facts_and_sealed_tamper_rejection(self):
        diagnostic = {'schema_version': 'p02-diagnostic-view-v1', 'scientific_validation': False}
        diagnostic['snapshot_sha256'] = fingerprint(diagnostic)
        catalog = copy.deepcopy(CATALOG)
        catalog['source_snapshots'] = {name: {'snapshot_sha256': diagnostic['snapshot_sha256'] if name == 'diagnostic' else None,
                                             'file_sha256': 'd' * 64}
                                       for name in ('diagnostic', 'inventory', 'baseline')}
        fake_catalog = SimpleNamespace(__file__=__file__, build_catalog=lambda *args: copy.deepcopy(catalog),
                                       validate_catalog=lambda value: None, read_facts=read_facts)
        with tempfile.TemporaryDirectory() as temp, patch.object(handoff, 'catalog_module', return_value=fake_catalog):
            root = Path(temp); loop = handoff.EvidenceHandoffCloudLoop(root / 'study')
            loop.study.create(root / 'diag', root / 'iter', root / 'base', root / 'inventory.json', '选择明确外部交接', 4)
            rows = []
            spec = {'max_requests': 4, 'model_identity': {'model': 'fixture-cloud'}}
            request_spec = {'reasoning_effort': 'high', 'context_tokens': 32768,
                            'max_output_tokens': 4096, 'max_request_bytes': 65536}
            for ordinal, name, params in [(1, 'read_evidence', {'fact_ids': ['f1', 'f2']}),
                                           (2, 'record_next_step', {'task_id': 'export_mapping', 'fact_ids': ['f1', 'f2']})]:
                state = loop.study.observe(); body = loop._request(state, 5 - ordinal, [], request_spec)
                reply = response(name, {**params, 'reason': '原始理由，未科学审定'})
                reply['message']['thinking'] = 'PRIVATE_THINKING_NOT_EXPORTED'
                decision = loop._parse_decision(reply, state, 'req' + str(ordinal), body)
                actual = loop.study.apply(decision)['action']
                rows.append({'ordinal': ordinal, 'status': 'applied', 'request_id': decision['request_id'],
                             'action_id': actual['id'], 'observation_json': canonical(state),
                             'request_json': canonical(body), 'request_sha256': fingerprint(body),
                             'response_json': canonical(reply), 'response_sha256': fingerprint(reply),
                             'decision_json': canonical(decision), 'error_code': None})
            final = loop.study.observe(); loop.db.write_bytes(b'fixture-native-journal')
            con = SimpleNamespace(execute=lambda sql: rows)
            fake_loop = SimpleNamespace(study=loop.study, db=loop.db,
                                        _connect=lambda: nullcontext(con),
                                        _state=lambda connection: ({'status': 'completed', 'reason': 'STUDY_PAUSED'}, spec, final),
                                        _parse_decision=loop._parse_decision,
                                        _validate_response=lambda response, spec: None)
            with patch.object(view, 'EvidenceHandoffCloudLoop', return_value=fake_loop):
                public = view.capture_handoff(loop.study.root, diagnostic)
                self.assertEqual(public['selected_task'], TASK)
                self.assertEqual(public['cited_facts'], FACTS[:2])
                self.assertTrue(public['waiting_for_external_input'])
                self.assertFalse(public['external_task_executed'])
                self.assertEqual(public['actions'][0]['result']['facts'][0]['provenance']['pointer'], '/first')
                self.assertEqual(public['execution']['applied_calls'], 2)
                self.assertNotIn('PRIVATE_THINKING_NOT_EXPORTED', canonical(public))
                output = root / 'publication'
                view.export_handoff(loop.study.root, diagnostic, output)
                artifacts = view.read_handoff_artifacts(output, diagnostic)
                self.assertIn('Map original exports', artifacts['handoff.md'].decode())
                self.assertIn('来源文件SHA256', artifacts['handoff.md'].decode())
                wrong = copy.deepcopy(diagnostic); wrong['extra'] = True
                wrong['snapshot_sha256'] = fingerprint({k: v for k, v in wrong.items() if k != 'snapshot_sha256'})
                with self.assertRaises(ResearchError): view.capture_handoff(loop.study.root, wrong)
                bad = json.loads(rows[1]['request_json'])
                context = json.loads(bad['messages'][1]['content']); context['catalog_snapshot_sha256'] = 'b' * 64
                bad['messages'][1]['content'] = canonical(context)
                rows[1]['request_json'] = canonical(bad); rows[1]['request_sha256'] = fingerprint(bad)
                with self.assertRaises(ResearchError): view.capture_handoff(loop.study.root, diagnostic)
                (output / 'handoff.md').write_bytes(artifacts['handoff.md'] + b'changed')
                with self.assertRaises(ResearchError): view.read_handoff_artifacts(output, diagnostic)
                without = {**public, 'selected_task': None, 'selected_action_id': None,
                           'cited_facts': [], 'model_reason_unreviewed': None, 'waiting_for_external_input': False}
                self.assertIn('尚无有效的任务交接', view._markdown(without).decode())


if __name__ == '__main__':
    unittest.main()
