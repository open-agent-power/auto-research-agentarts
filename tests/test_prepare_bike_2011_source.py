import csv
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from scripts import prepare_bike_2011_source as bike

ORIGINAL_CHECKED_ACQUISITION = bike._checked_acquisition


def generated_csv():
    out = io.StringIO(newline='')
    w = csv.writer(out, lineterminator='\n')
    w.writerow(['instant', 'dteday', 'workingday', 'temp', 'cnt', 'other'])
    for i in reversed(range(365)):
        d = datetime.date(2011, 1, 1) + datetime.timedelta(days=i)
        w.writerow([i, d.isoformat(), str(i % 2), '0.00' if i == 0 else f'{i/1000:.3f}', str(i), 'excluded'])
    w.writerow(['366', '2012-01-01', '1', '0.7', '999', 'excluded'])
    return out.getvalue().encode()


def make_zip(day=None, readme=b'Generated fixture; no license in this test README.\n', extra=()):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('day.csv', generated_csv() if day is None else day)
        z.writestr('Readme.txt', readme)
        for name, raw in extra:
            z.writestr(name, raw)
    return out.getvalue()


class BikeSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Only these isolated synthetic fixtures replace the production claim gate;
        # the executable CLI contains no option to bypass it.
        self.claim = patch.object(bike, '_production_claim', return_value=(self.root, {'commit': 'a'*40, 'preparation_sha256': bike.sha(Path(bike.__file__).read_bytes())}))
        self.claim.start()
        self.addCleanup(self.claim.stop)
        self.acquisition = patch.object(bike, '_checked_acquisition', side_effect=lambda path, workspace, identity, expected, acquired: ({'bytes': os.stat(path).st_size if Path(path).exists() else 1}, b'synthetic-receipt', b'synthetic-marker'))
        self.acquisition.start()
        self.addCleanup(self.acquisition.stop)

    def run_fixture(self, raw, *, expected=None, output='source'):
        path = self.root / ('input-' + hashlib.sha256(raw).hexdigest() + '.zip')
        path.write_bytes(raw)
        if output != 'source':
            case_root = self.root / output
            case_root.mkdir()
            self.claim.stop()
            self.claim = patch.object(bike, '_production_claim', return_value=(case_root, {'commit': 'a'*40, 'preparation_sha256': bike.sha(Path(bike.__file__).read_bytes())}))
            self.claim.start()
            return bike.prepare(path, case_root / 'source', expected_zip_sha256=expected or bike.sha(raw), acquired_at_utc='2026-11-15T12:00:00Z')
        return bike.prepare(path, self.root / output, expected_zip_sha256=expected or bike.sha(raw), acquired_at_utc='2026-11-15T12:00:00Z')

    def test_full_projection_provenance_capture_and_no_overwrite(self):
        raw = make_zip(); result = self.run_fixture(raw)
        d = self.root / 'source'
        with (d/'development/bike-2011.csv').open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 365)
        self.assertEqual(list(rows[0]), list(bike.COLUMNS))
        self.assertEqual((rows[0]['dteday'], rows[0]['temp'], rows[0]['cnt']), ('2011-01-01', '0.00', '0'))
        self.assertEqual(rows[-1]['dteday'], '2011-12-31')
        self.assertEqual((d/'original.zip').read_bytes(), raw)
        packet = json.loads((d/'source.json').read_bytes())
        self.assertEqual(packet['spec']['provenance']['origin_sha256'], bike.sha(generated_csv()))
        self.assertEqual(result['source_snapshot_sha256'], packet['snapshot_sha256'])
        self.assertEqual(result['license']['review_status'], 'operator_review_required')
        self.assertEqual(result['provenance_status'], 'official_https_acquisition_local_clock_not_independently_verified')
        self.assertIn('possible 2012', result['read_boundary'])
        for entry in result['files'].values():
            content = (d/entry['path']).read_bytes()
            self.assertEqual((entry['bytes'], entry['sha256']), (len(content), bike.sha(content)))
        before = {str(p.relative_to(d)): p.read_bytes() for p in d.rglob('*') if p.is_file()}
        with self.assertRaises(FileExistsError): self.run_fixture(raw)
        after = {str(p.relative_to(d)): p.read_bytes() for p in d.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_bad_sha_preserves_archive_and_failure(self):
        raw = make_zip()
        with self.assertRaisesRegex(ValueError, 'SHA or size mismatch'): self.run_fixture(raw, expected='0'*64)
        self.assertEqual((self.root/'source/original.zip').read_bytes(), raw)
        self.assertTrue((self.root/'source/failure.json').is_file())
        self.assertFalse((self.root/'source/receipt.json').exists())

    def test_duplicate_or_missing_dates_and_bad_groups_stop(self):
        lines = generated_csv().decode().splitlines()
        variants = [lines[:-2]+[lines[1],lines[-1]], lines[:-2]+[lines[-1]],
                    [x.replace(',0,0.00,', ',2,0.00,') for x in lines]]
        for i, variant in enumerate(variants):
            with self.subTest(i=i), self.assertRaises(ValueError):
                self.run_fixture(make_zip(('\n'.join(variant)+'\n').encode()), output=f'source{i}')
            self.assertTrue((self.root/f'source{i}/source/day.csv').exists())
            self.assertTrue((self.root/f'source{i}/source/failure.json').exists())

    def test_dangerous_zip_names_and_duplicate_members_stop(self):
        for i, extra in enumerate([(('../escape', b'x'),), (('DAY.CSV', b'x'),), (('nested/a', b'x'),)]):
            with self.subTest(i=i), self.assertRaises(ValueError): self.run_fixture(make_zip(extra=extra), output=f'source{i}')
            self.assertFalse((self.root/'escape').exists())

    def test_conflicting_or_unknown_license_stops_but_preserves_originals(self):
        for i, notice in enumerate((b'License: CC BY-NC 4.0\n', b'License: unknown\n', b'All rights reserved\n')):
            with self.subTest(i=i), self.assertRaises(ValueError): self.run_fixture(make_zip(readme=notice), output=f'source{i}')
            self.assertEqual((self.root/f'source{i}/source/README.txt').read_bytes(), notice)
            self.assertFalse((self.root/f'source{i}/source/receipt.json').exists())

    def test_symlink_and_oversized_input_rejected(self):
        source=self.root/'actual.zip';source.write_bytes(make_zip());link=self.root/'link.zip';link.symlink_to(source)
        with self.assertRaises(OSError): bike.prepare(link,self.root/'source',expected_zip_sha256=bike.sha(source.read_bytes()),acquired_at_utc='2026-11-15T12:00:00Z')
        source.write_bytes(b'x'*(bike.MAX_ZIP+1))
        other=self.root/'other';other.mkdir()
        with patch.object(bike, '_production_claim', return_value=(other, {'commit':'a'*40, 'preparation_sha256':'b'*64})):
            with self.assertRaises(ValueError): bike.prepare(source,other/'source',expected_zip_sha256='1'*64,acquired_at_utc='2026-11-15T12:00:00Z')
        self.assertTrue((other/'source/failure.json').exists())

    def test_symlink_parent_and_parent_traversal_rejected(self):
        source=self.root/'actual.zip'; source.write_bytes(make_zip())
        link=self.root/'linked'; link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            bike.prepare(link/'actual.zip',self.root/'source',expected_zip_sha256=bike.sha(source.read_bytes()),acquired_at_utc='2026-11-15T12:00:00Z')
        with self.assertRaises(ValueError):
            bike.prepare(source,self.root/'missing'/'..'/'source4',expected_zip_sha256=bike.sha(source.read_bytes()),acquired_at_utc='2026-11-15T12:00:00Z')

    def test_claim_and_exact_workspace_precede_any_source_read(self):
        with patch.object(bike, '_production_claim', side_effect=RuntimeError('bad claim')), patch.object(bike, '_bounded_file') as reader:
            with self.assertRaisesRegex(RuntimeError, 'bad claim'):
                bike.prepare(self.root/'missing.zip', self.root/'source', expected_zip_sha256='0'*64, acquired_at_utc='2026-11-15T12:00:00Z')
            reader.assert_not_called()
        self.assertFalse((self.root/'source').exists())
        with patch.object(bike, '_bounded_file') as reader:
            with self.assertRaisesRegex(ValueError, 'claimed workspace'):
                bike.prepare(self.root/'missing.zip', self.root/'elsewhere', expected_zip_sha256='0'*64, acquired_at_utc='2026-11-15T12:00:00Z')
            reader.assert_not_called()

    def test_claimed_attempt_marker_prevents_reprepare_after_directory_loss(self):
        raw = make_zip()
        self.run_fixture(raw)
        shutil.rmtree(self.root/'source')
        with patch.object(bike, '_bounded_file') as reader:
            with self.assertRaises(FileExistsError): self.run_fixture(raw)
            reader.assert_not_called()
        self.assertFalse((self.root/'source').exists())
        self.assertTrue((self.root/'source-preparation-started.json').exists())

    def test_production_cli_refuses_unclaimed_workspace(self):
        proc = subprocess.run([sys.executable, str(Path(bike.__file__).resolve()),
                '--prepare',
                '--zip', str(self.root/'no.zip'), '--output', str(self.root/'source'),
                '--expected-zip-sha256', '0'*64, '--acquired-at-utc', '2026-11-15T12:00:00Z'],
                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse((self.root/'source').exists())

    def test_claim_identity_drift_blocks_receipt_preserves_source(self):
        original = {'commit':'a'*40, 'preparation_sha256':'b'*64}
        changed = {'commit':'c'*40, 'preparation_sha256':'b'*64}
        with patch.object(bike, '_production_claim', side_effect=[(self.root, original), (self.root, changed)]):
            with self.assertRaisesRegex(ValueError, 'identity changed'):
                self.run_fixture(make_zip())
        self.assertTrue((self.root/'source/original.zip').exists())
        self.assertTrue((self.root/'source/failure.json').exists())
        self.assertFalse((self.root/'source/receipt.json').exists())

    def test_mock_https_acquisition_and_preparation_are_single_attempt(self):
        raw = make_zip()
        class Response(io.BytesIO):
            headers = {'Content-Length': str(len(raw)), 'Content-Encoding':'identity'}
            def geturl(self): return bike.URL
        class Opener:
            def open(self, request, timeout):
                self.url = request.full_url
                return Response(raw)
        opener=Opener()
        with patch.object(bike.urllib.request, 'build_opener', return_value=opener), patch.object(bike, '_checked_acquisition', wraps=ORIGINAL_CHECKED_ACQUISITION):
            receipt=bike.acquire()
            self.assertEqual((opener.url, receipt['bytes'], receipt['sha256']), (bike.URL, len(raw), bike.sha(raw)))
            prepared=bike.prepare(self.root/'acquisition/original.zip',self.root/'source',expected_zip_sha256=receipt['sha256'],acquired_at_utc=receipt['acquired_at_utc'])
        self.assertEqual(prepared['acquisition_receipt_sha256'],bike.sha((self.root/'acquisition/receipt.json').read_bytes()))
        with patch.object(bike.urllib.request, 'build_opener') as open_again:
            with self.assertRaises(FileExistsError): bike.acquire()
            open_again.assert_not_called()

    def test_official_redirect_and_partial_download_failure(self):
        self.assertTrue(bike._allowed_url(bike.URL))
        for url in ('http://archive.ics.uci.edu/x', 'https://archive.ics.uci.edu.evil/x', 'https://user@archive.ics.uci.edu/x'):
            self.assertFalse(bike._allowed_url(url))
        class Broken(io.BytesIO):
            headers={'Content-Length':'999', 'Content-Encoding':'identity'}
            def geturl(self): return bike.URL
        class Opener:
            def open(self, request, timeout): return Broken(b'part')
        with patch.object(bike.urllib.request, 'build_opener', return_value=Opener()):
            with self.assertRaisesRegex(ValueError, 'Incomplete'): bike.acquire()
        self.assertEqual((self.root/'acquisition/original.zip').read_bytes(),b'part')
        self.assertTrue((self.root/'source-acquisition-started.json').exists())
        self.assertFalse((self.root/'acquisition/receipt.json').exists())
        with self.assertRaises(FileExistsError): bike.acquire()

    def test_acquisition_receipt_drift_before_preparation_commit_stops(self):
        raw=make_zip()
        class Response(io.BytesIO):
            headers={'Content-Length':str(len(raw)), 'Content-Encoding':'identity'}
            def geturl(self): return bike.URL
        class Opener:
            def open(self, request, timeout): return Response(raw)
        original_capture=bike.adapter.capture_source
        def tamper_then_return(directory):
            packet=original_capture(directory)
            path=self.root/'acquisition/receipt.json'
            receipt=json.loads(path.read_bytes());receipt['final_url']='https://archive.ics.uci.edu/other'
            path.write_bytes(bike._json(receipt))
            return packet
        with patch.object(bike.urllib.request,'build_opener',return_value=Opener()), patch.object(bike,'_checked_acquisition',wraps=ORIGINAL_CHECKED_ACQUISITION):
            receipt=bike.acquire()
            with patch.object(bike.adapter,'capture_source',side_effect=tamper_then_return):
                with self.assertRaisesRegex(ValueError,'acquisition changed'):
                    bike.prepare(self.root/'acquisition/original.zip',self.root/'source',expected_zip_sha256=receipt['sha256'],acquired_at_utc=receipt['acquired_at_utc'])
        self.assertEqual((self.root/'source/original.zip').read_bytes(), raw)
        self.assertTrue((self.root/'source/failure.json').exists())
        self.assertFalse((self.root/'source/receipt.json').exists())

    def test_numeric_values_are_not_used_to_filter_or_impute(self):
        raw = make_zip(day=generated_csv().replace(b',0.00,0,', b',not-a-number,,', 1))
        self.run_fixture(raw)
        with (self.root/'source/development/bike-2011.csv').open(newline='') as stream:
            first=next(csv.DictReader(stream))
        self.assertEqual((first['temp'],first['cnt']),('not-a-number',''))


if __name__ == '__main__': unittest.main()
