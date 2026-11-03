import json
import unittest
from unittest.mock import patch

import test_chemotopo_iteration as fixture
from autoresearch.chemotopo_iteration_view import capture_iteration, load_iteration_view
from autoresearch.contracts import ResearchError, fingerprint, canonical


class IterationViewTests(unittest.TestCase):
    setUp = fixture.IterationTests.setUp

    def publication(self, manifest='c' * 64):
        value = {'prediction': {'manifest_sha256': manifest}}
        value['snapshot_sha256'] = fingerprint(value)
        return value

    def test_native_stop_is_bound_but_not_a_fit_or_memory_write(self):
        self.loop.run(fixture.Server(['stop']), max_new_requests=1, verified_weights=fixture.IDENTITY)
        with self.loop._connect(True) as con:
            row = con.execute('SELECT * FROM calls').fetchone()
            response = json.loads(row['response_json'])
            response['message']['thinking'] = 'private untrusted hidden reasoning'
            con.execute('UPDATE calls SET response_json=?,response_sha256=?', (canonical(response), fingerprint(response)))
        value, private = capture_iteration(self.root, self.publication())
        self.assertTrue(value['actions'][0]['model_selected'])
        self.assertEqual(value['execution']['completed_fits'], 0)
        self.assertEqual(value['execution']['requests_reserved'], 1)
        self.assertEqual(private['candidate_artifacts'], {})
        self.assertNotIn('private untrusted', json.dumps(value))
        self.assertNotIn(str(self.root), json.dumps(value))
        self.assertNotIn('memory', value)
        self.assertEqual(value['snapshot_sha256'], fingerprint({k: v for k, v in value.items() if k != 'snapshot_sha256'}))
        with self.assertRaises(ResearchError):
            load_iteration_view(self.root, self.publication('d' * 64))

    def test_changed_native_reason_or_input_cannot_claim_original_action(self):
        self.loop.run(fixture.Server(['stop']), max_new_requests=1, verified_weights=fixture.IDENTITY)
        with self.loop._connect(True) as con:
            row = dict(con.execute('SELECT * FROM calls').fetchone())
            response = json.loads(row['response_json'])
            response['message']['tool_calls'][0]['function']['arguments']['reason'] = 'Changed reason'
            con.execute('UPDATE calls SET response_json=?,response_sha256=?', (canonical(response), fingerprint(response)))
        with self.assertRaises(ResearchError):
            load_iteration_view(self.root, self.publication())
        with self.loop._connect(True) as con:
            con.execute('UPDATE calls SET response_json=?,response_sha256=?', (row['response_json'], row['response_sha256']))
            body = json.loads(row['request_json']); context = json.loads(body['messages'][1]['content'])
            context['prior_evidence']['primary_rule']['result'] = 'fabricated_improvement'
            body['messages'][1]['content'] = canonical(context)
            con.execute('UPDATE calls SET request_json=?,request_sha256=?', (canonical(body), fingerprint(body)))
        with self.assertRaises(ResearchError):
            load_iteration_view(self.root, self.publication())

    def test_partial_fit_reservation_is_not_completed_experiment(self):
        req = fixture.decision(self.loop.study, 'fit_alpha10', 'interrupted')
        with patch.object(fixture.study, '_calculate', side_effect=RuntimeError('interrupted')):
            with self.assertRaises(ResearchError):
                self.loop.study.apply(req)
        value = load_iteration_view(self.root, self.publication())
        self.assertEqual(value['execution']['fits_reserved'], 140)
        self.assertEqual(value['execution']['completed_fits'], 0)
        self.assertEqual(value['comparisons'], [])
        self.assertEqual(value['reservations'], [{'action': 'fit_alpha10', 'status': 'started'}])


if __name__ == '__main__':
    unittest.main()
