"""Owned local Ollama transport and weight provenance; no cloud credentials.

This is a Windows operator pilot. A loopback response alone is not evidence of a
real model: the caller separately records owned process, executable and blobs.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from .contracts import ResearchError, canonical
from .local_process import ManagedJob


MODEL = 'qwen3:4b'
MODEL_SOURCE = 'https://ollama.com/library/qwen3:4b'
PUBLISHER_MANIFEST_SHA256 = '359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7'
QWEN8_PUBLISHER_MANIFEST_SHA256 = '500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41'
MAX_JSON_BYTES = 2 * 1024 * 1024


def require(condition, code, message):
    if not condition: raise ResearchError(code, message)


def model_profile(model=MODEL):
    """Two reviewed local profiles, never an arbitrary model/URL or global switch."""
    require(type(model) is str and model in {MODEL, 'qwen3:8b'}, 'INVALID_MODEL', 'choose a reviewed pinned local model')
    large = model == 'qwen3:8b'
    return {'model': model, 'source_url': 'https://ollama.com/library/'+model,
            'publisher_manifest_sha256': QWEN8_PUBLISHER_MANIFEST_SHA256 if large else PUBLISHER_MANIFEST_SHA256,
            'manifest_relative_path': 'manifests/registry.ollama.ai/library/qwen3/'+('8b' if large else '4b'),
            'blob_limit': 6_000_000_000 if large else 4_000_000_000,
            'request_seconds': 300 if large else 180}


def regular(path, limit):
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        require(not item.is_symlink() and not getattr(item, 'is_junction', lambda: False)(), 'UNSAFE_PATH', 'local model paths cannot redirect')
    metadata = path.stat()
    require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1 and metadata.st_size <= limit,
            'UNSAFE_PATH', 'local model source must be a bounded unshared regular file')
    return path, metadata


def file_info(path, limit):
    path, before = regular(path, limit)
    digest = hashlib.sha256()
    prefix = bytearray()
    with path.open('rb') as stream:
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                (os.fstat(stream.fileno()).st_dev, os.fstat(stream.fileno()).st_ino,
                 os.fstat(stream.fileno()).st_size, os.fstat(stream.fileno()).st_mtime_ns),
                'MODEL_CHANGED', 'model source changed before opening')
        total = 0
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            require(total <= limit, 'MODEL_LIMIT', 'model source grew beyond its limit')
            digest.update(chunk)
            if len(prefix) < 65536: prefix.extend(chunk[:65536-len(prefix)])
    _, after = regular(path, limit)
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'MODEL_CHANGED', 'model source changed during hashing')
    return digest.hexdigest(), total, bytes(prefix)


def file_hash(path, limit):
    return file_info(path, limit)[:2]


def parse_json(payload):
    require(len(payload) <= MAX_JSON_BYTES, 'RESPONSE_TOO_LARGE', 'local JSON exceeds its byte cap')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'INVALID_JSON', 'duplicate local JSON field')
            value[key] = item
        return value
    def invalid(_): raise ResearchError('INVALID_JSON', 'nonfinite local JSON')
    try:
        result = json.loads(payload.decode('utf-8-sig'), object_pairs_hook=unique, parse_constant=invalid)
        canonical(result)  # Also rejects exponent-overflow infinities.
        return result
    except (ValueError, RecursionError): raise ResearchError('INVALID_JSON', 'local service returned invalid JSON') from None


def child_environment(cache, port, profile):
    # Do not forward provider API keys or account/session environment variables.
    allowed = {'SYSTEMROOT', 'WINDIR', 'PATH', 'PATHEXT', 'COMSPEC', 'TEMP', 'TMP',
               'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMW6432', 'PUBLIC',
               'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS'}
    result = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    result.update(OLLAMA_HOST=f'127.0.0.1:{port}', OLLAMA_MODELS=str(cache), OLLAMA_NO_CLOUD='1',
                  OLLAMA_NUM_PARALLEL='1', OLLAMA_MAX_LOADED_MODELS='1', OLLAMA_CONTEXT_LENGTH='4096', OLLAMA_KEEP_ALIVE='0')
    # Go's os.UserHomeDir on Windows uses USERPROFILE. Do not touch the real
    # user's Ollama key/config and never read/copy it into this task profile.
    profile = Path(profile).absolute()
    result.update(USERPROFILE=str(profile), APPDATA=str(profile/'AppData/Roaming'),
                  LOCALAPPDATA=str(profile/'AppData/Local'))
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        raise ResearchError('REDIRECT_DISABLED', 'local inference cannot redirect')


class LocalHTTP:
    def __init__(self, port):
        require(type(port) is int and 1024 <= port <= 65535, 'INVALID_REQUEST', 'use a bounded dedicated local port')
        self.port, self.endpoint = port, f'http://127.0.0.1:{port}'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def _blocking_request(self, route, body=None, *, timeout=30):
        require(route in {'/api/version', '/api/tags', '/api/show', '/api/chat', '/api/ps'}, 'INVALID_REQUEST', 'unsupported local model route')
        data = None if body is None else canonical(body).encode('utf-8')
        require(data is None or len(data) <= 65536, 'PROMPT_TOO_LARGE', 'local request exceeds 64KiB')
        request = urllib.request.Request(self.endpoint + route, data=data,
                                         headers={'Content-Type': 'application/json', 'User-Agent': 'AutoResearch-owned-local-pilot/1'})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                payload = response.read(MAX_JSON_BYTES + 1)
                require(response.status == 200, 'LOCAL_HTTP_FAILED', 'local model service did not return200')
            result = parse_json(payload)
            require(type(result) is dict, 'INVALID_JSON', 'local native API must return a JSON object')
            return result
        except ResearchError: raise
        except urllib.error.HTTPError as error:
            # Do not expose response snippets or headers to higher-level logs.
            raise ResearchError('LOCAL_HTTP_FAILED', 'local model HTTP status ' + str(error.code)) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ResearchError('LOCAL_REQUEST_UNKNOWN', 'local request failed or timed out; do not automatically resend inference') from None

    def request(self, route, body=None, *, timeout=30):
        """A native worker Job bounds headers AND body by a wall-clock deadline.

        Socket idle timeouts alone cannot bound a peer that keeps dripping bytes.
        Killing this owned HTTP worker never kills/adopts the responding service.
        """
        require(route in {'/api/version', '/api/tags', '/api/show', '/api/chat', '/api/ps'}, 'INVALID_REQUEST', 'unsupported local model route')
        require(type(timeout) in (int, float) and 0 < timeout <= 300, 'INVALID_REQUEST', 'local request deadline must be at most300seconds')
        require(body is None or len(canonical(body).encode('utf-8')) <= 65536, 'PROMPT_TOO_LARGE', 'local request exceeds64KiB')
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix='auto-research-local-http-') as directory:
            root = Path(directory)
            request_path = root/'request.json'
            request_path.write_text(canonical({'port': self.port, 'route': route, 'body': body, 'timeout': timeout}), encoding='utf-8')
            environment = child_environment(root/'unused-model-cache', self.port, root/'process-profile')
            environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
            with (root/'response.json').open('xb') as stdout, (root/'stderr.log').open('xb') as stderr, ManagedJob() as job:
                process = job.spawn([sys.executable, '-B', '-m', 'autoresearch.local_ollama', str(request_path)],
                                    env=environment, cwd=str(root), stdout=stdout, stderr=stderr)
                remaining = timeout - (time.monotonic() - started)
                try:
                    require(remaining > 0, 'LOCAL_REQUEST_UNKNOWN', 'local request deadline elapsed before dispatch; never automatically resend')
                    process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    raise ResearchError('LOCAL_REQUEST_UNKNOWN', 'local request reached its total deadline; never automatically resend inference') from None
            payload = (root/'response.json').read_bytes()
            require(len(payload) <= MAX_JSON_BYTES, 'RESPONSE_TOO_LARGE', 'local worker response exceeds its byte cap')
            envelope = parse_json(payload)
            require(type(envelope) is dict, 'LOCAL_REQUEST_UNKNOWN', 'local worker outcome is unavailable')
            if envelope.get('ok') is not True:
                raise ResearchError(envelope.get('code', 'LOCAL_REQUEST_UNKNOWN'), envelope.get('message', 'local request failed'))
            return envelope['result']


def listener_pid(port):
    require(os.name == 'nt', 'UNSUPPORTED_PLATFORM', 'this ownership probe is Windows-only')
    command = (f"@(Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort {int(port)} "
               "-ErrorAction Stop | Select-Object -ExpandProperty OwningProcess -Unique) | ConvertTo-Json -Compress")
    completed = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                               capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    require(completed.returncode == 0, 'OWNERSHIP_UNVERIFIED', 'cannot verify the local listening process')
    values = parse_json(completed.stdout)
    values = values if type(values) is list else [values]
    require(len(values) == 1 and type(values[0]) is int, 'OWNERSHIP_UNVERIFIED', 'local port has no unique verified owner')
    return values[0]


def verify_weights(cache, model=MODEL):
    profile = model_profile(model)
    publisher_sha = profile['publisher_manifest_sha256']
    cache = Path(cache).absolute()
    manifest_path = cache / profile['manifest_relative_path']
    manifest_sha, size, manifest_payload = file_info(manifest_path, 65536)
    manifest = parse_json(manifest_payload)
    require(type(manifest) is dict and type(manifest.get('layers')) is list and 1 <= len(manifest['layers']) <= 16
            and type(manifest.get('config')) is dict, 'INVALID_MODEL', 'unsupported local model manifest')
    records, licenses, model_files, captured_layers = [], [], [], {}
    for layer in [manifest['config'], *manifest['layers']]:
        require(type(layer) is dict and type(layer.get('digest')) is str
                and re.fullmatch(r'sha256:[0-9a-f]{64}', layer['digest']) is not None,
                'INVALID_MODEL', 'model blob requires a SHA256 address')
        path = cache / 'blobs' / layer['digest'].replace(':', '-')
        digest, length, prefix = file_info(path, profile['blob_limit'])
        require(digest == layer['digest'][7:] and type(layer.get('size')) is int and length == layer['size'],
                'MODEL_CHANGED', 'local model blob differs from its manifest')
        media_type = layer.get('mediaType', '')
        records.append({'digest': layer['digest'], 'media_type': media_type, 'bytes': length})
        captured_layers[layer['digest']] = prefix
        if media_type == 'application/vnd.ollama.image.model':
            require(prefix[:4] == b'GGUF', 'INVALID_MODEL', 'model payload is not GGUF weights')
            model_files.append(layer['digest'])
        if media_type == 'application/vnd.ollama.image.license':
            require(length <= 65536, 'INVALID_MODEL', 'model license exceeds its cap')
            licenses.append(prefix.decode('utf-8'))
    if manifest_sha == publisher_sha:
        publisher_payload = manifest_payload
    else:
        # Ollama0.40.11 retains the publisher manifest as a new provenance layer.
        # The two raw identities remain distinct; do not normalize away bytes.
        origins = [layer for layer in manifest['layers'] if layer.get('mediaType') == 'application/vnd.docker.distribution.manifest.v2+json']
        require(len(origins) == 1 and origins[0]['digest'] == 'sha256:'+publisher_sha
                and origins[0]['size'] <= 65536, 'MODEL_CHANGED', 'local wrapper lacks the exact checked publisher manifest')
        publisher_payload = captured_layers[origins[0]['digest']]
        publisher = parse_json(publisher_payload)
        require(type(publisher) is dict and manifest['config'] == publisher.get('config')
                and [layer for layer in manifest['layers'] if layer is not origins[0]] == publisher.get('layers'),
                'MODEL_CHANGED', 'local wrapper changes publisher model/config layers')
    require(hashlib.sha256(publisher_payload).hexdigest() == publisher_sha,
            'MODEL_CHANGED', 'publisher manifest bytes differ from the captured registry identity')
    require(len(model_files) == 1 and any('Apache License' in value and 'Version 2.0' in value for value in licenses),
            'INVALID_MODEL', 'checked Qwen3 weights and Apache2 license are required')
    require(file_hash(manifest_path, 65536)[0] == manifest_sha, 'MODEL_CHANGED', 'local manifest changed while checking its layers')
    return {'model': model, 'source_url': profile['source_url'], 'manifest_sha256': manifest_sha, 'manifest_bytes': size,
            'publisher_manifest_sha256': publisher_sha,
            'blobs': records, 'license': 'Apache-2.0 observed in captured model layer',
            'interpretation': 'Local content and process provenance, not a model-quality or scientific certification.'}


class OwnedOllama:
    """A task-owned hidden foreground server. Close its Job, never global services."""
    def __init__(self, executable, cache, output, *, port=11435, model=MODEL):
        self.model_profile = model_profile(model)
        self.model = self.model_profile['model']
        self.executable = Path(executable).absolute()
        self.cache, self.output = Path(cache).absolute(), Path(output).absolute()
        self.http = LocalHTTP(port)
        self.process = self.job = None
        self.handles = []
        self.stopped = False
        self.profile = None
        self.generated_task_key_files_removed = 0

    def __enter__(self):
        executable_sha, _ = file_hash(self.executable, 1_000_000_000)
        for path in (self.cache, self.output):
            for item in (path, *path.parents):
                require(not item.is_symlink() and not getattr(item, 'is_junction', lambda: False)(), 'UNSAFE_PATH', 'task paths cannot redirect')
            path.mkdir(parents=True, exist_ok=True)
        with socket.socket() as probe:
            try: probe.bind(('127.0.0.1', self.http.port))
            except OSError: raise ResearchError('PORT_BUSY', 'dedicated local port is already in use; do not adopt another server') from None
        profile = self.output/'process-profile'
        profile.mkdir()
        self.profile = profile
        self.environment = child_environment(self.cache, self.http.port, profile)
        self.job = ManagedJob()
        try:
            self.handles.append((self.output / 'server.stdout.log').open('xb'))
            self.handles.append((self.output / 'server.stderr.log').open('xb'))
            self.process = self.job.spawn([str(self.executable), 'serve'], env=self.environment,
                                          cwd=str(self.output), stdout=self.handles[0], stderr=self.handles[1])
            deadline = time.monotonic() + 45
            version = None
            while time.monotonic() < deadline:
                require(self.process.poll() is None, 'LOCAL_SERVER_FAILED', 'owned local server exited before readiness')
                try:
                    version = self.http.request('/api/version', timeout=1)
                    break
                except ResearchError:
                    time.sleep(.2)
            require(type(version) is dict and type(version.get('version')) is str,
                    'LOCAL_SERVER_FAILED', 'owned local server did not become ready within its bound')
            self.assert_owner()
            self.identity = {'server_pid': self.process.pid, 'executable_sha256': executable_sha,
                             'selected_model': self.model,
                             'ollama_version': version['version'], 'endpoint': self.http.endpoint,
                             'cloud_features_disabled_in_child_environment': True,
                             'isolated_process_profile': str(profile),
                             'child_environment_limits': {key: self.environment[key] for key in (
                                 'OLLAMA_NO_CLOUD', 'OLLAMA_NUM_PARALLEL', 'OLLAMA_MAX_LOADED_MODELS', 'OLLAMA_CONTEXT_LENGTH', 'OLLAMA_KEEP_ALIVE')},
                             'global_environment_or_services_changed': False}
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def assert_owner(self):
        require(self.process is not None and self.process.poll() is None
                and listener_pid(self.http.port) == self.process.pid,
                'OWNERSHIP_UNVERIFIED', 'inference endpoint is not owned by this foreground task')

    def acquire(self, *, timeout=1800):
        self.assert_owner()
        manifest = self.cache / self.model_profile['manifest_relative_path']
        if not manifest.exists():
            with (self.output / 'pull.stdout.log').open('xb') as stdout, (self.output / 'pull.stderr.log').open('xb') as stderr:
                worker = self.job.spawn([str(self.executable), 'pull', self.model], env=self.environment,
                                        cwd=str(self.output), stdout=stdout, stderr=stderr)
                try: code = worker.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    raise ResearchError('MODEL_DOWNLOAD_TIMEOUT', 'owned model download reached its time cap') from None
                require(code == 0, 'MODEL_DOWNLOAD_FAILED', 'official local model download failed; retain logs, do not call a paid fallback')
        self.assert_owner()
        weights = verify_weights(self.cache, self.model)
        shown = self.http.request('/api/show', {'model': self.model})
        with (self.output/'native-show-evidence.json').open('x', encoding='utf-8') as stream:
            json.dump(shown, stream, ensure_ascii=False, allow_nan=False, indent=2)
        require(type(shown.get('details')) is dict and shown['details'].get('family') == 'qwen3'
                and not shown.get('remote_model') and not shown.get('remote_host'), 'INVALID_MODEL', 'native model metadata does not match the checked local family')
        tags = self.http.request('/api/tags')
        with (self.output/'native-tags-evidence.json').open('x', encoding='utf-8') as stream:
            json.dump(tags, stream, ensure_ascii=False, allow_nan=False, indent=2)
        require(type(tags.get('models')) is list and all(type(item) is dict for item in tags['models'])
                and any(item.get('name') == self.model and item.get('digest') == weights['publisher_manifest_sha256'] for item in tags['models']),
                'MODEL_CHANGED', 'server model tag differs from the exact verified publisher manifest')
        weights['native_model_digest'] = weights['publisher_manifest_sha256']
        weights['native_digest_role'] = 'publisher manifest; distinct from the local provenance-wrapper file identity'
        self.show = shown
        return weights

    def __exit__(self, *_):
        try:
            if self.job is not None: self.job.close()
            if self.process is not None:
                self.process.wait(timeout=15)
                self.stopped = self.process.poll() is not None
            self._remove_task_keys()
        finally:
            for handle in self.handles: handle.close()
        return False

    def _remove_task_keys(self):
        # Only this freshly created task profile, never the user's .ollama.
        if self.profile is None: return
        require(self.profile == self.output/'process-profile', 'UNSAFE_PATH', 'task profile identity differs')
        for name in ('id_ed25519', 'id_ed25519.pub'):
            path = self.profile/'.ollama'/name
            if path.exists() or path.is_symlink():
                checked, _ = regular(path, 65536)  # Metadata only; never read a key.
                require(checked.is_relative_to(self.output), 'UNSAFE_PATH', 'generated task key must stay under its output')
                checked.unlink()
                self.generated_task_key_files_removed += 1


def _worker_main():
    try:
        path, _ = regular(sys.argv[1], 100000)
        request = parse_json(path.read_bytes())
        result = LocalHTTP(request['port'])._blocking_request(request['route'], request['body'], timeout=request['timeout'])
        envelope = {'ok': True, 'result': result}
    except (ResearchError, ValueError, OSError, KeyError) as error:
        envelope = {'ok': False, 'code': getattr(error, 'code', 'LOCAL_REQUEST_UNKNOWN'),
                    'message': str(error) if isinstance(error, ResearchError) else 'local worker failed; do not automatically resend'}
    sys.stdout.reconfigure(encoding='utf-8')
    print(canonical(envelope), end='')


if __name__ == '__main__': _worker_main()
