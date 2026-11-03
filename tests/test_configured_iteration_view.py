import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import nullcontext
from types import SimpleNamespace

from autoresearch import configured_iteration as execution
from autoresearch.configured_iteration_view import capture_configured
from autoresearch.chemotopo_iteration_view import _bind_native
from autoresearch.contracts import ResearchError, fingerprint, canonical
from test_configured_iteration import inputs, protocol


class ConfiguredViewTests(unittest.TestCase):
    def test_compact_selects_its_loop_context_and_marks_host_metadata(self):
        snapshot=inputs()
        class CompactFixture(execution.ConfiguredCloudLoop):
            def _connect(self):
                return nullcontext(SimpleNamespace(execute=lambda _:[]))
            def _state(self,con):
                return {'status':'active'},{'model_identity':{'model':'fixture'},'max_requests':4},self.study.observe()
        compact_context=lambda observation,remaining,errors:{'compact':True}
        module=SimpleNamespace(CompactCloudLoop=CompactFixture,project_context=compact_context)
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(execution.experiment_protocol,'prepare_inputs',return_value=snapshot), \
             patch.object(execution,'_validate_plan'):
            study=execution.ConfiguredStudy(Path(temp)/'study')
            study.create(Path(temp)/'source',Path(temp)/'baseline',Path(temp)/'interaction',protocol())
            publication={'prediction':{'manifest_sha256':snapshot['prior_evidence']['r54_manifest_sha256']}}
            publication['snapshot_sha256']=fingerprint(publication)
            legacy,_=capture_configured(study.root,publication)
            self.assertNotIn('native_interface',legacy['execution'])
            (study.root/'configured-cloud.sqlite').write_bytes(b'fixture journal')
            with patch.dict('sys.modules',{'autoresearch.compact_iteration':module}), \
                 patch('autoresearch.configured_iteration_view._bind_native',wraps=_bind_native) as binding:
                view,_=capture_configured(study.root,publication,native_interface='compact-v1')
            self.assertIsInstance(binding.call_args.args[0],CompactFixture)
            self.assertIs(binding.call_args.kwargs['context_builder'],compact_context)
            self.assertEqual(view['execution']['native_interface'],'compact-v1')
            metadata=view['execution']['native_metadata_binding']
            self.assertEqual(metadata['origin'],'host_bound_from_saved_observation')
            self.assertEqual(metadata['fields'],['observation_sha256','source_citation_ids','evidence_action_ids'])
            self.assertIn('不代表模型主动引用',metadata['notice'])
            self.assertEqual(view['execution']['applied_calls'],0)

    def test_unstarted_view_has_no_invented_calls_or_results(self):
        snapshot = inputs()
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(execution.experiment_protocol, 'prepare_inputs', return_value=snapshot), \
             patch.object(execution, '_validate_plan'):
            study = execution.ConfiguredStudy(Path(temp) / 'study')
            study.create(Path(temp) / 'source', Path(temp) / 'baseline', Path(temp) / 'interaction', protocol())
            publication = {'prediction': {'manifest_sha256': snapshot['prior_evidence']['r54_manifest_sha256']}}
            publication['snapshot_sha256'] = fingerprint(publication)
            view, private = capture_configured(study.root, publication)
            self.assertEqual(view['execution']['requests_reserved'], 0)
            self.assertEqual(view['execution']['completed_fits'], 0)
            self.assertEqual(view['comparisons'], [])
            self.assertEqual(view['controller_status'], 'not_started')
            self.assertNotIn(str(Path(temp)), canonical(view))
            self.assertEqual(json.loads(private['inputs_bytes']), snapshot)
            other = copy.deepcopy(publication); other['prediction']['manifest_sha256'] = 'f' * 64
            other['snapshot_sha256'] = fingerprint({k: v for k, v in other.items() if k != 'snapshot_sha256'})
            with self.assertRaises(ResearchError):
                capture_configured(study.root, other)

    def test_binding_uses_configured_context_and_rejects_hidden_feedback_change(self):
        state = {'configuration_sha256': 'a' * 64, 'prior_evidence': {'known_iterations': []},
                 'protocol': protocol(), 'inputs_sha256': 'b' * 64, 'actions': [], 'citations': [],
                 'budget': {'fits_reserved': 0, 'max_fits': 280}, 'reservations': [], 'endpoint_gate': {}, 'limits': []}
        state['observation_sha256'] = fingerprint(state)
        ctx = execution.project_context(state, 4, [])
        body = {'messages': [{'role': 'system', 'content': 'synthetic'}, {'role': 'user', 'content': canonical(ctx)}]}
        row = {'ordinal': 1, 'status': 'sending', 'observation_json': canonical(state), 'request_json': canonical(body),
               'request_sha256': fingerprint(body), 'response_json': None, 'response_sha256': None, 'action_id': None}
        bound, trace = _bind_native(None, state, {'max_requests': 4}, [row], context_builder=execution.project_context)
        self.assertEqual(bound, set()); self.assertEqual(trace[0]['status'], 'sending')
        ctx['prior_evidence'] = {'known_iterations': ['invented result']}
        body['messages'][1]['content'] = canonical(ctx)
        row.update(request_json=canonical(body), request_sha256=fingerprint(body))
        with self.assertRaises(ResearchError):
            _bind_native(None, state, {'max_requests': 4}, [row], context_builder=execution.project_context)


if __name__ == '__main__':
    unittest.main()
