"""Synthetic canonical request reconstruction; no execution or real research."""
import copy
import hashlib
import json
import sqlite3
import unittest

from autoresearch.contracts import canonical, fingerprint
from autoresearch.stored_project_history import _request_handoff, read_history


class StoredRequestHandoffTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:'); self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE requests(id TEXT PRIMARY KEY,digest TEXT,command TEXT,record TEXT)')
        self.project_id = 'project-fixture'; self.rid = 'original-request'
        self.proposal = {'choice': {'kind': 'wait'}, 'rationale': '<fixture>&not-html', 'version': 3}
        self.request = {'project_id': self.project_id, 'command': 'controller.advance_selection', 'need': 'next_check',
                        'expected_state_version': 12, 'proposal': self.proposal}
        self.parent = {'project_id': self.project_id, 'request_id': self.rid, 'request': self.request,
                       'request_sha256': fingerprint(self.request), 'code_identity': 'a' * 64,
                       'controller_code_identity': 'b' * 64, 'source_snapshot_sha256': 'c' * 64}
        self.body = {'request_id': self.rid, 'project_id': self.project_id, 'expected_state_version': 12, 'proposal': self.proposal}
        self.save_manager('advance', self.body)

    def save_manager(self, command, body, *, digest=None, intent_sha=None, project_id=None):
        digest = fingerprint(body) if digest is None else digest
        intent_sha = digest if intent_sha is None else intent_sha
        record = {'status': 'preparing', 'result': None, 'intent': {'project_id': project_id or self.project_id, 'request_sha256': intent_sha}}
        self.db.execute('INSERT OR REPLACE INTO requests VALUES(?,?,?,?)', (self.rid, digest, command, canonical(record)))

    def view(self, parent=None):
        return _request_handoff(self.parent if parent is None else parent, self.db, self.project_id)

    def test_selection_body_matches_both_purposes_and_keeps_canonical_bytes(self):
        value = self.view()
        self.assertEqual(value['status'], 'available')
        self.assertEqual(value['canonical_semantic_body'], self.body)
        self.assertEqual(value['canonical_semantic_json'], canonical(self.body))
        self.assertEqual(hashlib.sha256(value['canonical_semantic_json'].encode()).hexdigest(), value['manager_body_sha256'])
        self.assertEqual(value['manager_body_sha256'], value['manager_intent_sha256'])
        self.assertEqual(value['controller_request_sha256'], fingerprint(self.request))
        self.assertNotEqual(value['controller_request_sha256'], value['manager_body_sha256'])
        self.assertEqual((value['project_producer_code_identity'], value['controller_producer_code_identity']), ('a' * 64, 'b' * 64))

    def test_recipe_only_when_saved_recipe_and_proposal_bind(self):
        recipe = {'id': 'recipe-fixture', 'version': 2}
        request = {**self.request, 'command': 'controller.advance_recipe',
                   'recipe_decision': {'recipe': recipe, 'proposal': self.proposal}}
        parent = {**self.parent, 'request': request, 'request_sha256': fingerprint(request)}
        body = {'request_id': self.rid, 'project_id': self.project_id, 'expected_state_version': 12, 'recipe': recipe}
        self.save_manager('advance_recipe', body)
        self.assertEqual(self.view(parent)['canonical_semantic_body'], body)
        plan = {'request_id': 'fixture-plan', 'version': 1}
        parent.update(status='waiting', child_request_id=None, selection_context={'research_plan': plan})
        history = read_history(self.db, {'id': self.project_id, 'plan_revisions': [plan], 'controller_requests': [parent]}, [])
        self.assertEqual(history['plans'][0]['controllers'][0]['manager_receipt']['command'], 'advance_recipe')
        request = copy.deepcopy(request); request['recipe_decision']['proposal'] = copy.deepcopy(request['proposal'])
        request['recipe_decision']['proposal']['choice']['kind'] = 'execute'
        parent.update(request=request, request_sha256=fingerprint(request))
        self.assertEqual(self.view(parent)['status'], 'integrity_error')
        self.assertNotIn('canonical_semantic_body', self.view(parent))

    def test_missing_or_extra_fields_do_not_invent_a_request(self):
        cases = []
        for key in ('need', 'expected_state_version', 'proposal'):
            request = copy.deepcopy(self.request); request.pop(key)
            cases.append(request)
        cases.extend([{**self.request, 'need': 'other'}, {**self.request, 'expected_state_version': True}, {**self.request, 'extra': 'unrecorded'}])
        for request in cases:
            parent = {**self.parent, 'request': request, 'request_sha256': fingerprint(request)}
            value = self.view(parent)
            self.assertEqual(value['status'], 'partial')
            self.assertNotIn('canonical_semantic_body', value)
            self.assertNotIn('canonical_semantic_json', value)
        parent = {**self.parent, 'controller_code_identity': None}
        self.assertEqual(self.view(parent)['status'], 'partial')

    def test_tamper_and_cross_project_never_expose_body(self):
        parent = {**self.parent, 'request_sha256': '0' * 64}
        self.assertEqual(self.view(parent)['status'], 'integrity_error')
        self.save_manager('advance', self.body, digest='d' * 64, intent_sha='d' * 64)
        self.assertEqual(self.view()['status'], 'integrity_error')
        self.save_manager('advance', self.body, intent_sha='e' * 64)
        self.assertEqual(self.view()['status'], 'integrity_error')
        self.save_manager('advance', self.body, project_id='other-project')
        self.assertEqual(self.view()['status'], 'integrity_error')
        self.assertNotIn('canonical_semantic_json', self.view())

    def test_history_embeds_read_only_handoff_without_claiming_execution(self):
        plan = {'request_id': 'plan-1', 'version': 1}
        parent = {**self.parent, 'status': 'waiting', 'child_request_id': None,
                  'selection_context': {'research_plan': plan}, 'decision': {'next_action': {'kind': 'external_wait', 'execution_status': 'not_executed'}}}
        project = {'id': self.project_id, 'plan_revisions': [plan], 'controller_requests': [parent]}
        history = read_history(self.db, project, [])
        controller = history['plans'][0]['controllers'][0]
        self.assertEqual(controller['request_handoff']['canonical_semantic_body'], self.body)
        self.assertEqual(controller['status'], 'waiting')
        self.assertEqual(controller['child_binding_status'], 'explicit_null')
        self.assertIsNone(controller['matched_action'])


if __name__ == '__main__': unittest.main()
