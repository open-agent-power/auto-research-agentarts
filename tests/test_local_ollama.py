from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from autoresearch import local_ollama as module
from autoresearch.contracts import canonical, ResearchError


@contextmanager
def endpoint(body=b'{"version":"test-only-not-a-real-model"}', *, status=200, redirect=None):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def respond(self):
            requests.append(self.path)
            self.send_response(status)
            if redirect: self.send_header('Location', redirect)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        do_GET = do_POST = respond
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try: yield server.server_port, requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)


class LocalOllamaTests(unittest.TestCase):
    def synthetic_weights(self, root, model=module.MODEL):
        (root/'blobs').mkdir(exist_ok=True)
        records = []
        fake_gguf = b'GGUF-not-real-test-weights' + (b'-8b' if model == 'qwen3:8b' else b'')
        for payload, media in ((b'{}', 'application/vnd.docker.container.image.v1+json'),
                               (fake_gguf, 'application/vnd.ollama.image.model'),
                               (b'Apache License\nVersion 2.0 test fixture only', 'application/vnd.ollama.image.license')):
            digest = hashlib.sha256(payload).hexdigest()
            (root/'blobs'/('sha256-'+digest)).write_bytes(payload)
            records.append({'digest': 'sha256:'+digest, 'size': len(payload), 'mediaType': media})
        manifest = root/'manifests/registry.ollama.ai/library/qwen3'/model.split(':')[1]
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(canonical({'config': records[0], 'layers': records[1:]}), encoding='utf-8')
        return manifest, records

    def test_reviewed_profiles_pin_distinct_models_and_keep_default_patch_compatibility(self):
        expected = {
            'qwen3:4b': ('359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7', 4_000_000_000, 180),
            'qwen3:8b': ('500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41', 6_000_000_000, 300),
        }
        for model, (publisher, limit, seconds) in expected.items():
            with self.subTest(model=model):
                profile = module.model_profile(model)
                self.assertEqual(profile['model'], model)
                self.assertEqual(profile['source_url'], 'https://ollama.com/library/'+model)
                self.assertEqual(profile['publisher_manifest_sha256'], publisher)
                self.assertEqual(profile['blob_limit'], limit)
                self.assertEqual(profile['request_seconds'], seconds)
                self.assertTrue(profile['manifest_relative_path'].endswith('/'+model.split(':')[1]))
        self.assertEqual(module.model_profile(), module.model_profile('qwen3:4b'))
        with patch.object(module, 'PUBLISHER_MANIFEST_SHA256', 'a'*64):
            self.assertEqual(module.model_profile()['publisher_manifest_sha256'], 'a'*64)
            self.assertEqual(module.model_profile('qwen3:8b')['publisher_manifest_sha256'], expected['qwen3:8b'][0])
        self.assertEqual(module.MODEL, 'qwen3:4b')

    def test_unknown_models_are_rejected_before_files_or_processes_are_touched(self):
        with patch.object(module, 'file_info', side_effect=AssertionError('no source read')), \
             patch.object(module, 'ManagedJob', side_effect=AssertionError('no owned process')):
            for model in ('qwen3:9b', 'Qwen3:8b', 'qwen3:8b-cloud', 'https://example.invalid/model', '', None, True):
                for operation in (lambda: module.model_profile(model),
                                  lambda: module.verify_weights(Path('must-not-read'), model),
                                  lambda: module.OwnedOllama(sys.executable, 'must-not-read', 'must-not-create', model=model)):
                    with self.subTest(model=model), self.assertRaises(ResearchError) as error:
                        operation()
                    self.assertEqual(error.exception.code, 'INVALID_MODEL')

    def test_eight_billion_weight_identity_and_blob_limits_cannot_use_four_billion_pin(self):
        # Tiny fake GGUF bytes exercise provenance checks, not an actual model.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            small, _ = self.synthetic_weights(root)
            large, _ = self.synthetic_weights(root, 'qwen3:8b')
            small_sha = hashlib.sha256(small.read_bytes()).hexdigest()
            large_sha = hashlib.sha256(large.read_bytes()).hexdigest()
            self.assertNotEqual(small_sha, large_sha)
            with patch.object(module, 'PUBLISHER_MANIFEST_SHA256', small_sha), \
                 patch.object(module, 'QWEN8_PUBLISHER_MANIFEST_SHA256', large_sha):
                original = module.file_info
                with patch.object(module, 'file_info', wraps=original) as reads:
                    result = module.verify_weights(root, 'qwen3:8b')
                self.assertEqual(result['model'], 'qwen3:8b')
                self.assertEqual(result['source_url'], 'https://ollama.com/library/qwen3:8b')
                self.assertEqual(result['publisher_manifest_sha256'], large_sha)
                self.assertEqual(result['manifest_sha256'], large_sha)
                blob_reads = [call.args[1] for call in reads.call_args_list if call.args[0].parent.name == 'blobs']
                self.assertEqual(blob_reads, [6_000_000_000]*3)
                self.assertEqual(module.verify_weights(root)['publisher_manifest_sha256'], small_sha)
                for model, constant, wrong_sha in (('qwen3:8b', 'QWEN8_PUBLISHER_MANIFEST_SHA256', small_sha),
                                                   ('qwen3:4b', 'PUBLISHER_MANIFEST_SHA256', large_sha)):
                    with self.subTest(model=model), patch.object(module, constant, wrong_sha):
                        with self.assertRaises(ResearchError) as error: module.verify_weights(root, model)
                        self.assertEqual(error.exception.code, 'MODEL_CHANGED')

    def test_owned_eight_billion_acquire_uses_exact_native_tag_without_starting_a_server(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root/'cache'
            cache.mkdir()
            manifest, _ = self.synthetic_weights(cache, 'qwen3:8b')
            publisher = hashlib.sha256(manifest.read_bytes()).hexdigest()
            for index, tag in enumerate(({'name': 'qwen3:8b', 'digest': publisher},
                                         {'name': 'qwen3:4b', 'digest': publisher},
                                         {'name': 'qwen3:8b', 'digest': module.PUBLISHER_MANIFEST_SHA256})):
                output = root/str(index)
                output.mkdir()
                owned = module.OwnedOllama(sys.executable, cache, output, model='qwen3:8b')
                with self.subTest(tag=tag), patch.object(owned, 'assert_owner'), \
                     patch.object(module, 'QWEN8_PUBLISHER_MANIFEST_SHA256', publisher), \
                     patch.object(module, 'ManagedJob', side_effect=AssertionError('no server/download')), \
                     patch.object(owned.http, 'request', side_effect=[{'details': {'family': 'qwen3'}}, {'models': [tag]}]) as request:
                    if index == 0:
                        weights = owned.acquire()
                        self.assertEqual(weights['model'], 'qwen3:8b')
                        self.assertEqual(weights['native_model_digest'], publisher)
                    else:
                        with self.assertRaises(ResearchError) as error: owned.acquire()
                        self.assertEqual(error.exception.code, 'MODEL_CHANGED')
                    self.assertEqual(request.call_args_list[0].args, ('/api/show', {'model': 'qwen3:8b'}))
                    self.assertEqual(request.call_args_list[1].args, ('/api/tags',))
                    self.assertFalse((output/'pull.stdout.log').exists())

    @unittest.skipUnless(os.name == 'nt', 'total HTTP worker containment uses Windows Jobs')
    def test_transport_accepts_300_second_cap_but_rejects_larger_or_nonfinite_deadlines(self):
        with endpoint() as (port, requests):
            reply = module.LocalHTTP(port).request('/api/version', timeout=300)
            self.assertEqual(reply['version'], 'test-only-not-a-real-model')
            self.assertEqual(requests, ['/api/version'])
            with patch.object(module, 'ManagedJob', side_effect=AssertionError('invalid deadline must not dispatch')):
                for timeout in (301, 0, -1, True, float('nan'), float('inf')):
                    with self.subTest(timeout=timeout), self.assertRaises(ResearchError) as error:
                        module.LocalHTTP(port).request('/api/version', timeout=timeout)
                    self.assertEqual(error.exception.code, 'INVALID_REQUEST')
            self.assertEqual(requests, ['/api/version'])

    @unittest.skipUnless(os.name == 'nt', 'total HTTP worker containment uses Windows Jobs')
    def test_transport_is_literal_loopback_and_ignores_proxy_credentials(self):
        for port in ('https://example.invalid', True, 80, 70000):
            with self.assertRaises(ResearchError): module.LocalHTTP(port)
        with endpoint() as (port, requests):
            with patch.dict(os.environ, {'HTTP_PROXY': 'http://127.0.0.1:1', 'HTTPS_PROXY': 'http://127.0.0.1:1'}):
                reply = module.LocalHTTP(port).request('/api/version')
            self.assertEqual(reply['version'], 'test-only-not-a-real-model')
            self.assertEqual(requests, ['/api/version'])

    @unittest.skipUnless(os.name == 'nt', 'total HTTP worker containment uses Windows Jobs')
    def test_redirects_and_unapproved_routes_never_leave_owned_transport(self):
        with endpoint(status=302, redirect='https://example.invalid/paid') as (port, requests):
            with self.assertRaises(ResearchError) as error: module.LocalHTTP(port).request('/api/version')
            self.assertEqual(error.exception.code, 'REDIRECT_DISABLED')
            with self.assertRaises(ResearchError): module.LocalHTTP(port).request('/v1/cloud')
            self.assertEqual(requests, ['/api/version'])

    @unittest.skipUnless(os.name == 'nt', 'total HTTP worker containment uses Windows Jobs')
    def test_request_response_byte_caps_and_json_shape(self):
        with endpoint() as (port, requests):
            with self.assertRaises(ResearchError): module.LocalHTTP(port).request('/api/chat', {'text': 'x'*65536})
            self.assertEqual(requests, [])
        with endpoint(b'x'*(module.MAX_JSON_BYTES+1)) as (port, _):
            with self.assertRaises(ResearchError) as error: module.LocalHTTP(port).request('/api/version')
            self.assertEqual(error.exception.code, 'RESPONSE_TOO_LARGE')
        for payload in (b'[]', b'{"version":1,"version":2}', b'{"value":NaN}', b'\xff'):
            with endpoint(payload) as (port, _):
                with self.assertRaises(ResearchError) as error: module.LocalHTTP(port).request('/api/version')
                self.assertEqual(error.exception.code, 'INVALID_JSON')

    @unittest.skipUnless(os.name == 'nt', 'total HTTP worker containment uses Windows Jobs')
    def test_error_body_not_exposed_and_unknown_request_not_retried(self):
        with endpoint(b'private-response-marker', status=503) as (port, requests):
            with self.assertRaises(ResearchError) as error: module.LocalHTTP(port).request('/api/chat', {'model': module.MODEL})
            self.assertEqual(error.exception.code, 'LOCAL_HTTP_FAILED')
            self.assertNotIn('private-response-marker', str(error.exception))
            self.assertEqual(requests, ['/api/chat'])
        client = module.LocalHTTP(11435)
        with patch.object(client.opener, 'open', side_effect=TimeoutError) as request:
            with self.assertRaises(ResearchError) as error: client._blocking_request('/api/chat', {'model': module.MODEL})
            self.assertEqual(error.exception.code, 'LOCAL_REQUEST_UNKNOWN')
            self.assertEqual(request.call_count, 1)

    def test_child_environment_excludes_provider_keys_and_forces_local_only(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'unit-test-placeholder', 'OLLAMA_API_KEY': 'unit-test-placeholder',
                                    'OLLAMA_HOST': 'https://example.invalid', 'OLLAMA_NO_CLOUD': '0'}):
            env = module.child_environment(Path('owned-cache'), 11435, Path('owned-profile'))
        self.assertNotIn('OPENAI_API_KEY', env)
        self.assertNotIn('OLLAMA_API_KEY', env)
        self.assertEqual(env['OLLAMA_HOST'], '127.0.0.1:11435')
        self.assertEqual(env['OLLAMA_NO_CLOUD'], '1')
        self.assertEqual(env['OLLAMA_KEEP_ALIVE'], '0')
        self.assertEqual(env['USERPROFILE'], str(Path('owned-profile').absolute()))
        self.assertEqual(env['APPDATA'], str(Path('owned-profile/AppData/Roaming').absolute()))
        self.assertNotIn('HOME', env)

    def test_cleanup_removes_only_fresh_task_keys_without_reading_default_user_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root/'owned-output'
            profile = output/'process-profile'
            (profile/'.ollama').mkdir(parents=True)
            generated = profile/'.ollama/id_ed25519'
            generated.write_text('unit-test-placeholder-not-a-key', encoding='utf-8')
            default = root/'default-user/.ollama/id_ed25519'
            default.parent.mkdir(parents=True)
            default.write_text('unrelated-unit-placeholder', encoding='utf-8')
            owned = module.OwnedOllama(sys.executable, root/'cache', output)
            owned.profile = profile
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('no key content read')):
                owned._remove_task_keys()
            self.assertFalse(generated.exists())
            self.assertTrue(default.exists())
            self.assertEqual(owned.generated_task_key_files_removed, 1)

    def test_model_manifest_and_blobs_are_checked_not_model_quality(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, records = self.synthetic_weights(root)
            publisher = hashlib.sha256(manifest.read_bytes()).hexdigest()
            with patch.object(module, 'PUBLISHER_MANIFEST_SHA256', publisher):
                result = module.verify_weights(root)
                self.assertEqual(len(result['blobs']), 3)
                self.assertNotIn('actual_inference_verified', result)
                weights = root/'blobs'/records[1]['digest'].replace(':', '-')
                weights.write_bytes(b'GGUF-modified')
                with self.assertRaises(ResearchError) as error: module.verify_weights(root)
                self.assertEqual(error.exception.code, 'MODEL_CHANGED')

    def test_manifest_replacement_after_capture_cannot_mix_old_hash_and_new_layers(self):
        # A coherent captured payload may not be replaced between hashing and
        # parsing. No model weights or native inference are involved here.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, _ = self.synthetic_weights(root)
            publisher = hashlib.sha256(manifest.read_bytes()).hexdigest()
            original = module.file_info
            calls = []
            def change(path, limit):
                result = original(path, limit)
                if Path(path) == manifest and not calls:
                    calls.append(True)
                    changed = json.loads(manifest.read_text(encoding='utf-8'))
                    changed['layers'].reverse()
                    manifest.write_text(canonical(changed), encoding='utf-8')
                return result
            with patch.object(module, 'file_info', side_effect=change), patch.object(module, 'PUBLISHER_MANIFEST_SHA256', publisher):
                with self.assertRaises(ResearchError) as error: module.verify_weights(root)
            self.assertEqual(error.exception.code, 'MODEL_CHANGED')

    def test_local_wrapper_preserves_both_raw_identities_and_exact_publisher_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, _ = self.synthetic_weights(root)
            publisher_payload = manifest.read_bytes()
            publisher_sha = hashlib.sha256(publisher_payload).hexdigest()
            (root/'blobs'/('sha256-'+publisher_sha)).write_bytes(publisher_payload)
            wrapper = json.loads(publisher_payload)
            wrapper['layers'].append({'mediaType': 'application/vnd.docker.distribution.manifest.v2+json',
                                     'digest': 'sha256:'+publisher_sha, 'size': len(publisher_payload)})
            manifest.write_text(canonical(wrapper), encoding='utf-8')
            with patch.object(module, 'PUBLISHER_MANIFEST_SHA256', publisher_sha):
                result = module.verify_weights(root)
                self.assertEqual(result['publisher_manifest_sha256'], publisher_sha)
                self.assertNotEqual(result['manifest_sha256'], publisher_sha)
                wrapper['layers'][:2] = reversed(wrapper['layers'][:2])
                manifest.write_text(canonical(wrapper), encoding='utf-8')
                with self.assertRaises(ResearchError) as error: module.verify_weights(root)
                self.assertEqual(error.exception.code, 'MODEL_CHANGED')

    @unittest.skipUnless(os.name == 'nt', 'total HTTP worker containment uses Windows Jobs')
    def test_total_deadline_covers_slow_response_headers_and_body_without_retry(self):
        for drip_headers in (True, False):
            requests = []
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_): pass
                def do_GET(self):
                    requests.append(self.path)
                    body = b'{"value":"'+b'x'*80+b'"}'
                    header = b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'
                    try:
                        if not drip_headers: self.connection.sendall(header)
                        for byte in header if drip_headers else body:
                            self.connection.sendall(bytes([byte]))
                            time.sleep(.04)
                    except OSError: pass
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                started = time.monotonic()
                with self.assertRaises(ResearchError) as error:
                    module.LocalHTTP(server.server_port).request('/api/version', timeout=.7)
                elapsed = time.monotonic()-started
                self.assertEqual(error.exception.code, 'LOCAL_REQUEST_UNKNOWN')
                self.assertLess(elapsed, 1.8)
                self.assertEqual(requests, ['/api/version'])
            finally:
                server.shutdown()
                server.server_close()
                worker.join(5)

    @unittest.skipUnless(os.name == 'nt', 'owned server lifecycle is Windows-only')
    def test_busy_port_is_not_adopted_or_stopped(self):
        with tempfile.TemporaryDirectory() as directory, socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            server = module.OwnedOllama(sys.executable, Path(directory)/'cache', Path(directory)/'output', port=listener.getsockname()[1])
            with patch.object(module, 'ManagedJob', side_effect=AssertionError('do not start another process')):
                with self.assertRaises(ResearchError) as error: server.__enter__()
            self.assertEqual(error.exception.code, 'PORT_BUSY')
            self.assertIsNone(server.process)

    def test_probe_schema_limits_scope_without_choosing_query_or_action(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
        from probe_local_research import schema_for
        schema = schema_for({'observation_sha256': 'a'*64})
        actions = {value for branch in schema['oneOf'] for value in branch['properties']['action']['enum']}
        self.assertEqual(actions, {'search', 'pause', 'stop'})
        search = schema['oneOf'][0]['properties']['parameters']['properties']['query']
        self.assertEqual(search, {'type': 'string'})
        self.assertTrue(all(branch['properties']['observation_sha256']['enum'] == ['a'*64] for branch in schema['oneOf']))

    def test_every_schema_reference_kind_executes_real_c01_search_contract(self):
        import test_c01_research as fixture
        from autoresearch.c01_model_loop import _decision
        from autoresearch.knowledge import KINDS
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
        from probe_local_research import schema_for
        base = fixture.C01ResearchTests('test_terminal_decision_is_durable_and_stops_new_dispatch')
        base.setUp()
        try:
            kinds = schema_for(base.study.observe())['oneOf'][0]['properties']['parameters']['properties']['kinds']['items']['enum']
            self.assertEqual(set(kinds), KINDS)
            self.assertNotIn('official_md', kinds)
            self.assertNotIn('project_profile', kinds)
            for kind in kinds:
                observation = base.study.observe()
                content = canonical({'observation_sha256': observation['observation_sha256'], 'action': 'search',
                    'reason': 'Synthetic schema-to-actual-reference contract check, not a real model decision.',
                    'source_citation_ids': [], 'evidence_action_ids': [], 'parameters': {'query': 'C01 alloy', 'kinds': [kind], 'limit': 1}})
                decision = _decision(content, observation, 'schema-kind-' + kind)
                result = base.study.apply(decision)
                self.assertEqual(result['action']['parameters']['kinds'], [kind])
        finally: base.doCleanups()


if __name__ == '__main__': unittest.main()
