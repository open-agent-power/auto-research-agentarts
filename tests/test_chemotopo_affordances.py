import copy
import tempfile
import unittest
from pathlib import Path

from autoresearch import chemotopo_cloud as cloud
from autoresearch import c01_native_tools
from autoresearch.contracts import ResearchError
from autoresearch.research_memory import ResearchMemory
from test_chemotopo_study import fixture_environment, request
from test_chemotopo_cloud import IDENTITY, response


class ChemoTopoAffordanceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        environment = fixture_environment()
        environment.__enter__()
        self.addCleanup(environment.__exit__, None, None, None)
        self.root = Path(directory.name) / 'study'
        self.loop = cloud.ChemoTopoCloudLoop(self.root)
        self.loop.study.create('fixture-source', 'Inspect and compare conditional evidence.')
        self.loop.configure(IDENTITY, max_requests=8)

    def apply(self, action):
        self.loop.study.apply(request(self.loop.study, action, action))
        return self.loop.study.observe()

    def body(self, state, remaining=8):
        with self.loop._connect() as con:
            _, spec, _ = self.loop._state(con)
        return self.loop._request(state, remaining, [], spec)

    def test_prerequisites_and_completion_change_offered_tools(self):
        state = self.loop.study.observe()
        available = set(cloud.affordances(state)['available_tools'])
        self.assertIn('inspect_source', available)
        self.assertTrue({'compare_policies', 'remember_evidence', 'recall_evidence'}.isdisjoint(available))
        state = self.apply('inspect_source')
        available = set(cloud.affordances(state)['available_tools'])
        self.assertNotIn('inspect_source', available)
        self.assertTrue({'compare_policies', 'review_evidence'} <= available)
        self.assertNotIn('remember_evidence', available)
        state = self.apply('compare_policies')
        availability = cloud.affordances(state)
        self.assertNotIn('compare_policies', availability['available_tools'])
        self.assertIn('remember_evidence', availability['available_tools'])
        self.assertTrue(availability['memory_readiness']['numerical_prerequisites_complete'])
        self.assertFalse(availability['memory_readiness']['remember_action_committed'])
        state = self.apply('remember_evidence')
        availability = cloud.affordances(state)
        self.assertNotIn('remember_evidence', availability['available_tools'])
        self.assertIn('recall_evidence', availability['available_tools'])
        self.assertEqual(availability['memory_readiness']['active_observation_count'], 2)

    def test_recall_snapshot_and_retirement_reopen_or_close_recall(self):
        for action in ('inspect_source', 'compare_policies', 'remember_evidence', 'recall_evidence'):
            state = self.apply(action)
        availability = cloud.affordances(state)
        self.assertTrue(availability['memory_readiness']['current_snapshot_explicitly_recalled'])
        self.assertNotIn('recall_evidence', availability['available_tools'])
        memory = ResearchMemory(self.root / 'observation-memory')
        entries = state['memory_context']['entries']
        memory.set_status(entries[0]['id'], 'retired', 'Fixture withdrawal', 'retire-one')
        state = self.loop.study.observe()
        self.assertIn('recall_evidence', cloud.affordances(state)['available_tools'])
        memory.set_status(entries[1]['id'], 'retired', 'Fixture withdrawal', 'retire-two')
        availability = cloud.affordances(self.loop.study.observe())
        self.assertEqual(availability['memory_readiness']['active_observation_count'], 0)
        self.assertNotIn('recall_evidence', availability['available_tools'])

    def test_pause_stop_and_terminal_tools_at_each_stage(self):
        state = self.loop.study.observe()
        for action in (None, 'inspect_source', 'compare_policies', 'remember_evidence', 'recall_evidence'):
            if action:
                state = self.apply(action)
            self.assertTrue({'pause', 'stop'} <= set(cloud.affordances(state)['available_tools']))
            terminal = cloud.affordances(state, terminal=True)
            self.assertEqual(set(terminal['available_tools']), {'pause', 'stop'})
            tools = c01_native_tools.tools_from_schema(cloud.schema_for(state, terminal=True))
            self.assertEqual({tool['function']['name'] for tool in tools}, {'pause', 'stop'})

    def test_native_schema_requires_correct_namespaces_and_latest_feedback(self):
        self.apply('inspect_source')
        state = self.apply('compare_policies')
        body = self.body(state)
        tool = next(t['function'] for t in body['tools'] if t['function']['name'] == 'remember_evidence')
        properties = tool['parameters']['properties']
        source = state['citations'][0]['citation_id']
        old, latest = [a['id'] for a in state['actions']]
        self.assertEqual(properties['source_citation_ids']['items']['enum'], [c['citation_id'] for c in state['citations']])
        self.assertEqual(properties['evidence_action_ids']['contains']['enum'], [latest])
        good = response(body, 'remember_evidence')
        parsed = self.loop._parse_decision(good, state, 'good', body)
        self.assertEqual(parsed['evidence_action_ids'], [latest])
        cases = [({'source_citation_ids': [latest]}, 'INVALID_EVIDENCE'),
                 ({'evidence_action_ids': [source]}, 'INVALID_EVIDENCE'),
                 ({'evidence_action_ids': [old]}, 'LATEST_FEEDBACK_REQUIRED'),
                 ({'source_citation_ids': []}, 'INVALID_EVIDENCE')]
        for change, code in cases:
            with self.subTest(change=change):
                forged = copy.deepcopy(good)
                forged['message']['tool_calls'][0]['function']['arguments'].update(change)
                before = copy.deepcopy((forged, state, body))
                with self.assertRaises(ResearchError) as error:
                    self.loop._parse_decision(forged, state, 'bad', body)
                self.assertEqual(error.exception.code, code)
                self.assertEqual((forged, state, body), before)
        self.assertEqual(len(self.loop.study.observe()['actions']), 2)

    def test_memory_id_is_not_a_source_or_action_and_no_repair(self):
        for action in ('inspect_source', 'compare_policies', 'remember_evidence'):
            state = self.apply(action)
        body = self.body(state)
        memory_id = state['memory_context']['entries'][0]['id']
        for key in ('source_citation_ids', 'evidence_action_ids'):
            with self.subTest(key=key):
                forged = response(body, 'review_evidence')
                forged['message']['tool_calls'][0]['function']['arguments'][key] = [memory_id]
                original = copy.deepcopy(forged)
                with self.assertRaises(ResearchError) as error:
                    self.loop._parse_decision(forged, state, 'bad-memory', body)
                self.assertEqual(error.exception.code, 'INVALID_EVIDENCE')
                self.assertEqual(forged, original)
        self.assertEqual(len(self.loop.study.observe()['actions']), 3)


if __name__ == '__main__':
    unittest.main()
