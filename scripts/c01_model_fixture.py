"""Literal-loopback scripted C01 endpoint; deliberately not a language model."""
from contextlib import contextmanager
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

KEY_ENV = 'C01_MODEL_FIXTURE_KEY'
FIXTURE_KEY = 'c01-fixture-only-not-a-real-model-key'


def configuration(endpoint):
    return {'connection': {'endpoint': endpoint, 'model': 'scripted-c01-not-an-llm', 'api_key_env': KEY_ENV,
                           'allow_loopback_http': True, 'max_output_tokens': 1024, 'max_prompt_bytes': 64000,
                           'output_token_parameter': 'max_completion_tokens', 'timeout_seconds': 10},
            'pricing': {'input_cny_per_million': '1', 'output_cny_per_million': '1', 'input_tokens_ceiling': 64000,
                        'source_url': 'https://example.invalid/c01-fixture-simulated-prices',
                        'input_ceiling_source_url': 'https://example.invalid/c01-fixture-simulated-ceiling',
                        'checked_on': date.today().isoformat(), 'verified': True,
                        'output_cap_covers_all_billed_tokens': True}}


def decision(context):
    actions = context['actions']
    fits = [action for action in actions if action['action'] == 'fit']
    cited = context['known_source_citation_ids'][:2]
    evidence = [context['latest_experiment_id']] if context['latest_experiment_id'] else []
    value = {'observation_sha256': context['observation_sha256'], 'source_citation_ids': cited,
             'evidence_action_ids': evidence, 'parameters': {}}
    if not actions:
        return {**value, 'action': 'search', 'reason': 'FIXTURE retrieve C01 source conditions before numerical work.',
                'parameters': {'query': 'C01 alloy', 'kinds': ['reuse_note'], 'limit': 2}}
    if not cited:
        return {**value, 'action': 'stop', 'reason': 'FIXTURE no compatible source was retrieved; do not invent evidence.'}
    if not fits:
        return {**value, 'action': 'fit', 'reason': 'FIXTURE baseline after the actual retrieved source IDs.',
                'parameters': {'alpha': 1.0, 'features': ['ecm_gpa', 'yield_mpa', 'water_contact_angle_deg', 'sfe_owrk_total_mn_m'],
                               'hypothesis': 'Measure four-feature prediction errors under frozen leave-one-alloy-out evaluation.',
                               'expected_effect': 'Compare to fold means; worse errors and domain violations remain evidence.'}}
    if not any(action['action'] == 'residuals' for action in actions):
        fit = fits[-1]
        worse = sum(not metric['better_than_baseline'] for metric in fit['metrics'])
        return {**value, 'action': 'residuals', 'parameters': {'fit_action_id': fit['id']},
                'reason': f'FIXTURE observed {worse}/4 targets not below baseline; inspect actual error concentration.'}
    if not any(action['action'] == 'correlation' for action in actions):
        return {**value, 'action': 'correlation', 'reason': 'FIXTURE inspect the fixed pair after actual residual feedback; no causal claim.'}
    pair = next(action for action in actions if action['action'] == 'correlation')
    return {**value, 'action': 'stop', 'reason': f"FIXTURE stop after observed r={pair['pearson_r']:.6g}; reused eight-alloy feedback is not independent validation."}


@contextmanager
def model_fixture(mode='normal', *, policy=None):
    if mode not in {'normal', 'always_invalid', 'invalid_first', 'http_error', 'over_input'}:
        raise ValueError('unsupported fixture mode')
    if policy is not None and not callable(policy): raise ValueError('fixture policy must be an operator-provided callable')
    records, lock = [], threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit() or not 1 <= int(lengths[0]) <= 64000:
                self.send_error(400)
                return
            self.connection.settimeout(5)
            raw = self.rfile.read(int(lengths[0]))
            payload = json.loads(raw)
            context = json.loads(payload['messages'][-1]['content'])
            with lock:
                ordinal = len(records) + 1
                record = {'ordinal': ordinal, 'request_id': self.headers.get('X-Request-ID'),
                          'path': self.path, 'payload': payload, 'fixture': True}
                records.append(record)
            if mode == 'http_error':
                self.send_response(503); self.send_header('Content-Length', '0'); self.end_headers()
                return
            chosen = (decision if policy is None else policy)(context)
            content = json.dumps(chosen, ensure_ascii=False)
            if mode == 'always_invalid' or mode == 'invalid_first' and ordinal == 1:
                content = '{"action":[]}'
            prompt = 65000 if mode == 'over_input' else 200
            response = {'id': 'c01-fixture-response-' + str(ordinal), 'model': 'scripted-c01-not-an-llm',
                        'choices': [{'message': {'role': 'assistant', 'content': content}}],
                        'usage': {'prompt_tokens': prompt, 'completion_tokens': 100, 'total_tokens': prompt + 100}}
            record['response'] = response
            encoded = json.dumps(response, ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(encoded))); self.end_headers(); self.wfile.write(encoded)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    worker.start()
    try: yield f'http://127.0.0.1:{server.server_port}/openai/v1/chat/completions', records
    finally:
        server.shutdown(); server.server_close(); worker.join(5)
