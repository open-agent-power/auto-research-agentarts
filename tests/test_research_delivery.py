import copy
from contextlib import contextmanager
import hashlib
import http.client
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from autoresearch.c01_studio import create_server
from autoresearch.contracts import fingerprint
from autoresearch.research_delivery import load_research_delivery
from autoresearch.research_memory import derive_entries
import test_c01_research_outputs as record_fixture
import test_c01_studio as legacy_fixture


class ResearchDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        record_fixture.C01ResearchOutputsTests.setUpClass()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.legacy = legacy_fixture.C01StudioTests('test_routes_are_read_only_and_exports_belong_to_c01')
        self.legacy.setUp()
        self.addCleanup(self.legacy.tearDown)
        self.archive_sha = hashlib.sha256(self.legacy.source.read_bytes()).hexdigest()
        self.record = copy.deepcopy(record_fixture.C01ResearchOutputsTests.record)
        self.reproduction = copy.deepcopy(record_fixture.C01ResearchOutputsTests.reproduction)
        self.record['archive_sha256'] = self.archive_sha
        self.reproduction['inputs']['source']['archive_sha256'] = self.archive_sha
        self.reproduction['inputs_sha256'] = fingerprint(self.reproduction['inputs'])
        self.delivery = self.root / 'delivery'
        self.delivery.mkdir()
        package = self.root / 'package'
        package.mkdir()
        fixture = record_fixture.C01ResearchOutputsTests('test_independent_recompute_all_recipes_metrics_and_diagnostics')
        fixture.package(package)
        (package / 'research.json').write_text(json.dumps(self.record), encoding='utf-8')
        (package / 'reproduction.json').write_text(json.dumps(self.reproduction), encoding='utf-8')
        fixture.seal_package(package)
        contents = {path.relative_to(package).as_posix(): path.read_bytes() for path in package.rglob('*') if path.is_file()}
        archive = BytesIO()
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as writer:
            for name, payload in contents.items(): writer.writestr(name, payload)
        files = {'研究记录.json': contents['research.json'], '复现输入.json': contents['reproduction.json'],
                 '研究报告.pdf': contents['paper.pdf'], '图表摘要.png': contents['figures/comparison.png'],
                 '指标对照.csv': contents['comparison.csv'], '复现附件.zip': archive.getvalue()}
        derived = derive_entries(self.record, self.reproduction)
        entries = [{'record': entry, 'inclusion_status': 'active', 'source_versions': [entry['provenance']]}
                   for entry in derived['entries']]
        # A valid historical first-fit source remains attached after the final export.
        prefix = copy.deepcopy(self.record)
        prefix.update(fits=prefix['fits'][:1], diagnostics=[], decisions=prefix['decisions'][:2],
                      status='active', origin_observation_sha256='1' * 64)
        historical = copy.deepcopy(entries[0]['record']['provenance'])
        historical.update(source_record_sha256=fingerprint(prefix), origin_observation_sha256=prefix['origin_observation_sha256'])
        entries[0]['record'] = copy.deepcopy(entries[0]['record'])
        entries[0]['record']['provenance'] = historical
        entries[0]['source_versions'] = [historical, derived['entries'][0]['provenance']]
        self.memory = {'scope': derived['scope'], 'condition_match': 'exact', 'entries': entries,
                       'scientific_validation': False, 'warning': 'Historical untrusted recall; not a live memory database.'}
        files['研究记忆.json'] = json.dumps(self.memory).encode()
        files['记忆验证.json'] = json.dumps({'scope': derived['scope'], 'entries': len(entries), 'scientific_validation': False}).encode()
        for name, payload in files.items(): (self.delivery / name).write_bytes(payload)
        self.seal()

    def seal(self):
        files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in self.delivery.iterdir() if path.name != '交付清单.json'}
        (self.delivery / '交付清单.json').write_text(json.dumps({
            'delivery_kind': 'local_verified_artifacts_not_cloud_deployment', 'scientific_validation': False,
            'files': files}), encoding='utf-8')

    @contextmanager
    def server(self, mount=True):
        # Renderer mocks isolate HTTP and loading behavior, never generate a PDF.
        with patch('autoresearch.c01_studio.render_report', return_value=b'%PDF legacy report'), \
             patch('autoresearch.c01_studio.reproduction', return_value=b'legacy ZIP'):
            server = create_server(self.legacy.root, self.legacy.source, 0,
                                   research_delivery=self.delivery if mount else None)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try: yield server
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)

    def request(self, server, path, method='GET', headers=None, body=None):
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally: conn.close()

    def hashes(self, root):
        return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in root.rglob('*') if path.is_file()}

    def test_load_checks_numerical_record_and_accepts_prefix_source_version(self):
        before = self.hashes(self.delivery)
        loaded = load_research_delivery(self.delivery, self.archive_sha)
        self.assertEqual(loaded['research'], self.record)
        self.assertEqual(loaded['memory'], self.memory)
        self.assertEqual(loaded['validation']['fold_fits_performed'], 64)
        self.assertEqual(loaded['memory']['entries'][0]['source_versions'][1]['source_record_sha256'], fingerprint(self.record))
        self.assertNotEqual(loaded['memory']['entries'][0]['record']['provenance']['source_record_sha256'], fingerprint(self.record))
        self.assertEqual(self.hashes(self.delivery), before)

    def test_http_frozen_routes_readonly_guards_and_legacy_identity(self):
        before, legacy_before = self.hashes(self.delivery), self.hashes(self.legacy.root)
        with self.server() as server, patch('autoresearch.research_delivery.derive_entries', side_effect=AssertionError('GET must not recompute')):
            status, _, body = self.request(server, '/api/c01/research')
            self.assertEqual(status, 200)
            response = json.loads(body)
            self.assertTrue(response['enabled'])
            self.assertEqual(response['research'], self.record)
            self.assertEqual(response['memory'], self.memory)
            self.assertFalse(response['validation']['scientific_validation'])
            self.assertEqual(json.loads(self.request(server, '/api/c01/research/memory')[2]), self.memory)
            for route, filename in (('report.pdf', '研究报告.pdf'), ('reproduction.zip', '复现附件.zip'), ('comparison.png', '图表摘要.png')):
                status, headers, body = self.request(server, '/api/c01/research/' + route)
                self.assertEqual(status, 200)
                self.assertEqual(body, (self.delivery / filename).read_bytes())
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
            self.assertEqual(json.loads(self.request(server, '/api/c01')[2]), self.legacy.summary)
            self.assertEqual(self.request(server, '/api/c01/report.pdf')[2], b'%PDF legacy report')
            self.assertEqual(self.request(server, '/api/c01/reproduction.zip')[2], b'legacy ZIP')
            self.assertEqual(json.loads(self.request(server, '/api/c01/continuation')[2]), {'enabled': False})
            self.assertEqual(self.request(server, '/api/export/paper.pdf')[0], 404)
            for path in ('/api/c01/research', '/api/c01/research/memory', '/api/c01/research/step'):
                self.assertEqual(self.request(server, path, 'POST', body=b'{}')[0], 405)
            bad_host = {'Host': 'attacker.example'}
            self.assertEqual(self.request(server, '/api/c01/research', headers=bad_host)[0], 403)
            self.assertEqual(self.request(server, '/api/c01/research', 'POST', bad_host)[0], 403)
            self.assertEqual(self.request(server, '/api/c01/research', 'POST', {'Origin': 'https://attacker.example'})[0], 403)
            self.assertEqual(self.request(server, '/api/c01/research/%2e%2e/research.json')[0], 404)
        self.assertEqual(self.hashes(self.delivery), before)
        self.assertEqual(self.hashes(self.legacy.root), legacy_before)

    def test_restart_and_source_changes_never_mix_frozen_bytes(self):
        with self.server() as first:
            initial = self.request(first, '/api/c01/research')[2]
        with self.server() as restarted:
            self.assertEqual(self.request(restarted, '/api/c01/research')[2], initial)
            original_pdf = self.request(restarted, '/api/c01/research/report.pdf')[2]
            (self.delivery / '研究报告.pdf').write_bytes(b'changed after startup')
            (self.delivery / '研究记录.json').write_bytes(b'{}')
            self.assertEqual(self.request(restarted, '/api/c01/research')[2], initial)
            self.assertEqual(self.request(restarted, '/api/c01/research/report.pdf')[2], original_pdf)
        with self.assertRaises(ValueError): load_research_delivery(self.delivery, self.archive_sha)

    def test_no_mount_and_optional_memory_are_explicit(self):
        with self.server(mount=False) as server:
            for path in ('/api/c01/research', '/api/c01/research/memory'):
                self.assertEqual(json.loads(self.request(server, path)[2]), {'enabled': False})
            self.assertEqual(self.request(server, '/api/c01/research/report.pdf')[0], 404)
        for name in ('研究记忆.json', '记忆验证.json'): (self.delivery / name).unlink()
        self.seal()
        with self.server() as server:
            self.assertIsNone(json.loads(self.request(server, '/api/c01/research')[2])['memory'])
            self.assertEqual(json.loads(self.request(server, '/api/c01/research/memory')[2]), {'enabled': False})

    def test_hash_wrong_archive_unknown_members_and_partial_memory_fail_closed(self):
        with self.assertRaises(ValueError): load_research_delivery(self.delivery, '9' * 64)
        original = (self.delivery / '图表摘要.png').read_bytes()
        (self.delivery / '图表摘要.png').write_bytes(b'changed')
        with self.assertRaises(ValueError): load_research_delivery(self.delivery, self.archive_sha)
        (self.delivery / '图表摘要.png').write_bytes(original)
        (self.delivery / 'private.txt').write_text('not public')
        with self.assertRaises(ValueError): load_research_delivery(self.delivery, self.archive_sha)
        (self.delivery / 'private.txt').unlink()
        (self.delivery / '记忆验证.json').unlink()
        self.seal()
        with self.assertRaises(ValueError): load_research_delivery(self.delivery, self.archive_sha)

    def test_resealed_scope_payload_status_and_provenance_are_not_trusted(self):
        mutations = (lambda m: m['scope'].update(inputs_sha256='9' * 64),
                     lambda m: m.update(scientific_validation=True),
                     lambda m: m['entries'][0].update(inclusion_status='retired'),
                     lambda m: m['entries'][0]['record']['payload']['metrics'][0].update(mae=999),
                     lambda m: m['entries'][0]['record'].update(review_status='scientifically_reviewed'),
                     lambda m: m['entries'][0].update(source_versions=m['entries'][0]['source_versions'][:1]),
                     lambda m: m['entries'][0]['record'].update(provenance={
                         **m['entries'][0]['record']['provenance'], 'origin_observation_sha256': '9' * 64}))
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                memory = copy.deepcopy(self.memory)
                mutate(memory)
                (self.delivery / '研究记忆.json').write_text(json.dumps(memory), encoding='utf-8')
                self.seal()
                with self.assertRaises(ValueError): load_research_delivery(self.delivery, self.archive_sha)

    def test_resealed_report_zip_mismatch_and_linked_files_are_rejected(self):
        original = (self.delivery / '研究报告.pdf').read_bytes()
        (self.delivery / '研究报告.pdf').write_bytes(b'other report')
        self.seal()
        with self.assertRaises(ValueError): load_research_delivery(self.delivery, self.archive_sha)
        (self.delivery / '研究报告.pdf').write_bytes(original)
        self.seal()
        other = self.root / 'other-report.pdf'
        other.write_bytes(original)
        (self.delivery / '研究报告.pdf').unlink()
        os.link(other, self.delivery / '研究报告.pdf')
        with self.assertRaises(ValueError): load_research_delivery(self.delivery, self.archive_sha)
        self.assertEqual(other.read_bytes(), original)

    def test_manifest_paths_and_duplicate_json_keys_are_rejected(self):
        manifest = self.delivery / '交付清单.json'
        value = json.loads(manifest.read_text(encoding='utf-8'))
        value['files']['../outside'] = '9' * 64
        manifest.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaises(ValueError): load_research_delivery(self.delivery, self.archive_sha)
        manifest.write_bytes(b'{"files":{},"files":{}}')
        with self.assertRaises(ValueError): load_research_delivery(self.delivery, self.archive_sha)


if __name__ == '__main__':
    unittest.main()
