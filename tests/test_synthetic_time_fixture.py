"""Fixed invented hourly fixture: preparation/verification only, no research."""
import csv
from datetime import datetime, timedelta
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid
from contextlib import ExitStack
from unittest.mock import patch

from autoresearch import numeric_association_adapter as association
from autoresearch import relevance_retrieval_adapter as relevance
from autoresearch import retrieval_lexical as lexical
from autoresearch import staged_relevance_adapter as staged
from autoresearch import tabular_quality_adapter as tabular
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.project_controller import ProjectController
from autoresearch.research_project import ResearchProject
import scripts.prepare_synthetic_time_fixture as preparer


class SyntheticTimeFixtureTests(unittest.TestCase):
    def output(self):
        path = Path(__file__).resolve().parents[1] / 'runs' / ('s134-synthetic-time-' + uuid.uuid4().hex)
        self.assertFalse(path.exists())
        self.addCleanup(lambda: shutil.rmtree(path) if path.exists() and not path.is_symlink() else None)
        return path

    def forbid_research(self, stack):
        for target in ('socket.socket.connect', 'socket.create_connection', 'urllib.request.urlopen', 'subprocess.Popen'):
            stack.enter_context(patch(target, side_effect=AssertionError('network or subprocess forbidden')))
        for name in ('create', 'step', 'read_evidence'):
            stack.enter_context(patch.object(ResearchProject, name, side_effect=AssertionError(name + ' forbidden')))
        stack.enter_context(patch.object(ProjectController, '_dispatch', side_effect=AssertionError('dispatch forbidden')))
        stack.enter_context(patch.object(tabular, 'execute', side_effect=AssertionError('quality action forbidden')))
        stack.enter_context(patch.object(association, 'execute', side_effect=AssertionError('association forbidden')))
        stack.enter_context(patch.object(staged, 'execute', side_effect=AssertionError('staged action forbidden')))
        stack.enter_context(patch.object(staged.AUDIT, 'execute_saved', side_effect=AssertionError('audit forbidden')))
        stack.enter_context(patch.object(relevance, 'retrieve', side_effect=AssertionError('ranking forbidden')))
        for name in ('build_index', 'retrieve', 'metrics'):
            stack.enter_context(patch.object(lexical, name, side_effect=AssertionError(name + ' forbidden')))

    @staticmethod
    def csv_rows(raw):
        return list(csv.reader(io.StringIO(raw.decode('utf-8'), newline=''), strict=True))

    @staticmethod
    def csv_bytes(rows):
        stream = io.StringIO(newline='')
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerows(rows)
        return stream.getvalue().encode('utf-8')

    def test_fixed_fixture_contains_exact_naive_hourly_sequence_and_missing(self):
        with ExitStack() as stack:
            self.forbid_research(stack)
            raw, spec = preparer._fixture()
            inspected = preparer._inspect_csv(raw)
        self.assertIsInstance(inspected, dict)
        self.assertIsInstance(spec, bytes)
        rows = self.csv_rows(raw)
        self.assertEqual(rows[0], ['station','year','month','day','hour','x','outcome'])
        self.assertEqual(len(rows), 29)
        start = datetime(2024, 2, 28, 22)
        for index, row in enumerate(rows[1:]):
            hour = start + timedelta(hours=index)
            self.assertEqual(row[:5], ['SYNTHETIC_S1', f'{hour.year:04d}', f'{hour.month:02d}', f'{hour.day:02d}', f'{hour.hour:02d}'])
            self.assertEqual(row[5:], ['NA' if index == 4 else str(index), '' if index == 9 else str(2 * index)])
        self.assertEqual(rows[1][5:], ['0', '0'])
        self.assertEqual(rows[-1][1:5], ['2024','03','01','01'])
        self.assertEqual(sum(row[5] == 'NA' for row in rows[1:]), 1)
        self.assertEqual(sum(row[6] == '' for row in rows[1:]), 1)

    def test_private_inspection_rejects_time_station_and_numeric_corruption(self):
        raw, _ = preparer._fixture(); rows = self.csv_rows(raw)
        variants = []
        variants.append(rows[:8] + rows[9:])             # missing hour
        variants.append(rows[:8] + [rows[7][:]] + rows[8:])  # duplicate hour
        moved = [r[:] for r in rows]; moved[2], moved[3] = moved[3], moved[2]; variants.append(moved)
        for col, value in ((0,'SYNTHETIC_S2'), (1,'2023'), (2,'13'), (3,'30'), (4,'24'),
                           (1,'2025'), (2,'2'), (4,'2'), (5,'NaN'), (5,'inf'), (5,'-inf'),
                           (5,'1e999'), (5,'bad'), (6,'NaN'), (6,'inf')):
            changed = [r[:] for r in rows]
            # Index 2 falls on leap day and index 1 includes explicit zero.
            changed[2][col] = value
            variants.append(changed)
        leap = [r[:] for r in rows]; leap[3][1:5] = ['2023','02','29','00']; variants.append(leap)
        outside = [r[:] for r in rows]; outside[-1][1:5] = ['2024','03','01','02']; variants.append(outside)
        wrong_header = [r[:] for r in rows]; wrong_header[0][5] = 'unexpected'; variants.append(wrong_header)
        with ExitStack() as stack:
            self.forbid_research(stack)
            for index, altered in enumerate(variants):
                with self.subTest(variant=index):
                    with self.assertRaises(ValueError): preparer._inspect_csv(self.csv_bytes(altered))
            with self.assertRaises(ValueError): preparer._inspect_csv(b'\xff')

    def test_capture_load_identity_verify_and_deterministic_outputs(self):
        left, right = self.output(), self.output()
        with ExitStack() as stack:
            self.forbid_research(stack)
            receipt_left = preparer.prepare(left)
            receipt_right = preparer.prepare(right)
            self.assertEqual(preparer.verify(left), receipt_left)
            self.assertEqual(preparer.verify(right), receipt_right)
            left_files = {str(p.relative_to(left)): p.read_bytes() for p in left.rglob('*') if p.is_file()}
            right_files = {str(p.relative_to(right)): p.read_bytes() for p in right.rglob('*') if p.is_file()}
            self.assertEqual(left_files, right_files)
            self.assertEqual(set(left_files), {'claim.json','source.csv','spec.json','source.json','report.json','receipt.json'})
            raw_csv, raw_spec = preparer._fixture()
            self.assertEqual(left_files['source.csv'], raw_csv)
            self.assertEqual(left_files['spec.json'], raw_spec)
            packet = json.loads(left_files['source.json'])
            self.assertEqual(tabular.load_source(left_files['source.json']), packet)
            self.assertEqual(tabular.capture_source(left), packet)
            self.assertEqual(packet['source']['sha256'], hashlib.sha256(raw_csv).hexdigest())
            self.assertEqual(packet['spec_source']['sha256'], hashlib.sha256(raw_spec).hexdigest())
            self.assertEqual(packet['snapshot_sha256'], json.loads(left_files['source.json'])['snapshot_sha256'])
            self.assertEqual(receipt_left, receipt_right)
            self.assertEqual(json.loads(left_files['receipt.json']), receipt_left)
            report = json.loads(left_files['report.json'])
            self.assertEqual(set(report), {'schema_version','synthetic_only','config','config_sha256','csv_sha256',
                             'spec_sha256','packet_sha256','source_snapshot_sha256','scope_sha256','generator_sha256',
                             'recalculator_sha256','tabular_identity','facts','limitations'})
            self.assertTrue(report['synthetic_only'])
            self.assertEqual(report['config']['station'], 'SYNTHETIC_S1')
            self.assertEqual(report['config']['clock'], 'synthetic_naive_clock_no_timezone_no_dst')
            self.assertEqual(report['config']['start'], '2024-02-28T22:00:00')
            self.assertEqual(report['config']['end_exclusive'], '2024-03-01T02:00:00')
            self.assertEqual(report['config_sha256'], fingerprint(report['config']))
            self.assertEqual(report['csv_sha256'], hashlib.sha256(raw_csv).hexdigest())
            self.assertEqual(report['spec_sha256'], hashlib.sha256(raw_spec).hexdigest())
            self.assertEqual(report['packet_sha256'], hashlib.sha256(left_files['source.json']).hexdigest())
            self.assertEqual(report['source_snapshot_sha256'], packet['snapshot_sha256'])
            self.assertEqual(report['scope_sha256'], fingerprint(packet['scope']))
            self.assertEqual(report['generator_sha256'], hashlib.sha256(Path(preparer.__file__).read_bytes()).hexdigest())
            self.assertEqual(report['recalculator_sha256'], hashlib.sha256(Path(preparer.checker.__file__).read_bytes()).hexdigest())
            self.assertEqual(report['tabular_identity'], tabular.code_identity())
            self.assertEqual(report['facts'], {'rows':28, 'hours_expected':28,
                'numeric_counts':{'x':{'finite':27,'zero':1,'empty':0,'declared_missing':1},
                                  'outcome':{'finite':27,'zero':1,'empty':1,'declared_missing':0}},
                'paired_finite':26, 'paired_excluded':2})
            self.assertEqual(receipt_left['files'], {name:hashlib.sha256(left_files[name]).hexdigest()
                             for name in ('claim.json','source.csv','spec.json','source.json','report.json')})
            self.assertEqual(receipt_left['report_sha256'], hashlib.sha256(left_files['report.json']).hexdigest())
            self.assertEqual(receipt_left['packet_sha256'], report['packet_sha256'])
            self.assertEqual(receipt_left['source_snapshot_sha256'], packet['snapshot_sha256'])
            self.assertEqual((receipt_left['research_dispatches'],receipt_left['model_calls'],receipt_left['fits']), (0,0,0))

    def test_source_replacement_before_and_after_capture_fails_closed(self):
        capture = tabular.capture_source
        for when in ('before','after'):
          for asset in ('source.csv','spec.json'):
            with self.subTest(when=when, asset=asset):
                output = self.output()
                def replace(directory):
                    path = Path(directory) / asset
                    def alter():
                        if asset == 'source.csv':
                            path.write_bytes(path.read_bytes().replace(b',0,0\n', b',5,0\n', 1))
                        else:
                            obj = json.loads(path.read_bytes()); obj['dataset_label'] += ' changed'
                            path.write_text(canonical(obj), encoding='utf-8')
                    if when == 'before':
                        alter()
                    packet = capture(directory)
                    if when == 'after':
                        alter()
                    return packet
                with ExitStack() as stack:
                    self.forbid_research(stack)
                    stack.enter_context(patch.object(tabular, 'capture_source', side_effect=replace))
                    with self.assertRaises((ValueError, ResearchError, OSError)):
                        preparer.prepare(output)
                self.assertTrue(output.is_dir())
                self.assertFalse((output / 'receipt.json').exists())
                with self.assertRaises((ValueError, FileExistsError, OSError)):
                    preparer.prepare(output)

    def test_source_or_packet_drift_after_report_before_receipt_stops(self):
        for filename in ('source.csv','source.json'):
            with self.subTest(filename=filename):
                output = self.output(); sync = preparer._sync_directory; invoked = []
                def mutate_before_receipt(path):
                    if Path(path) == output and not invoked:
                        invoked.append(True)
                        target = output / filename
                        target.write_bytes(target.read_bytes() + b' ')
                    return sync(path)
                with ExitStack() as stack:
                    self.forbid_research(stack)
                    stack.enter_context(patch.object(preparer, '_sync_directory', side_effect=mutate_before_receipt))
                    with self.assertRaises((ValueError, ResearchError, OSError)):
                        preparer.prepare(output)
                self.assertTrue(invoked)
                self.assertTrue(output.is_dir())
                self.assertFalse((output / 'receipt.json').exists())
                with self.assertRaises((ValueError, FileExistsError, OSError)):
                    preparer.prepare(output)

    def test_checker_or_adapter_identity_drift_before_receipt_stops(self):
        for key in ('recalculator_sha256','tabular_identity'):
            with self.subTest(key=key):
                output = self.output()
                initial = preparer._identities()
                changed = dict(initial); changed[key] = '0' * 64
                with ExitStack() as stack:
                    self.forbid_research(stack)
                    stack.enter_context(patch.object(preparer, '_identities', side_effect=[initial,changed]))
                    with self.assertRaises((ValueError, ResearchError, OSError)):
                        preparer.prepare(output)
                self.assertTrue(output.is_dir())
                self.assertFalse((output / 'receipt.json').exists())
                with self.assertRaises((ValueError, FileExistsError, OSError)):
                    preparer.prepare(output)

    def test_producer_identity_drift_during_verify_stops(self):
        output = self.output()
        with ExitStack() as stack:
            self.forbid_research(stack)
            preparer.prepare(output)
            identities = preparer._identities()
            changed = dict(identities); changed['recalculator_sha256'] = '0' * 64
            before = {str(p.relative_to(output)): p.read_bytes() for p in output.rglob('*') if p.is_file()}
            with patch.object(preparer, '_identities', side_effect=[identities, changed]):
                with self.assertRaises(ValueError): preparer.verify(output)
            self.assertEqual(before, {str(p.relative_to(output)): p.read_bytes() for p in output.rglob('*') if p.is_file()})

    def test_each_original_file_drift_rejected_without_repair(self):
        for filename in ('claim.json','source.csv','spec.json','source.json','report.json','receipt.json'):
            with self.subTest(filename=filename):
                output = self.output()
                with ExitStack() as stack:
                    self.forbid_research(stack)
                    preparer.prepare(output)
                    target = output / filename; target.write_bytes(target.read_bytes() + b' ')
                    damaged = {str(p.relative_to(output)): p.read_bytes() for p in output.rglob('*') if p.is_file()}
                    with self.assertRaises((ValueError, ResearchError, OSError)): preparer.verify(output)
                self.assertEqual(damaged, {str(p.relative_to(output)): p.read_bytes() for p in output.rglob('*') if p.is_file()})

    def test_changed_station_or_clock_is_rejected_before_directory_creation(self):
        for field, value in (('clock','unknown'), ('station','SYNTHETIC_S2')):
            with self.subTest(field=field):
                output = self.output()
                with ExitStack() as stack:
                    self.forbid_research(stack)
                    stack.enter_context(patch.dict(preparer.CONFIG, {field:value}))
                    with self.assertRaises((ValueError, ResearchError)):
                        preparer.prepare(output)
                self.assertFalse(output.exists())
                self.assertFalse(output.is_symlink())

    def test_unexpected_file_directory_or_symlink_stops_verification_without_repair(self):
        for mode in ('file','directory','symlink'):
            with self.subTest(mode=mode):
                output = self.output()
                with ExitStack() as stack:
                    self.forbid_research(stack)
                    preparer.prepare(output)
                    extra = output / 'unexpected'
                    if mode == 'file':
                        extra.write_bytes(b'synthetic extra')
                    elif mode == 'directory':
                        extra.mkdir(); (extra / 'child').write_bytes(b'synthetic extra')
                    else:
                        temporary = Path(stack.enter_context(tempfile.TemporaryDirectory()))
                        target = temporary / 'target'; target.write_bytes(b'untouched')
                        extra.symlink_to(target)
                    before = {p.name:(('link',str(p.readlink())) if p.is_symlink() else
                                       ('directory',sorted(c.name for c in p.iterdir())) if p.is_dir() else
                                       ('file',p.read_bytes())) for p in output.iterdir()}
                    with self.assertRaises((ValueError, ResearchError, OSError)):
                        preparer.verify(output)
                    after = {p.name:(('link',str(p.readlink())) if p.is_symlink() else
                                      ('directory',sorted(c.name for c in p.iterdir())) if p.is_dir() else
                                      ('file',p.read_bytes())) for p in output.iterdir()}
                    self.assertEqual(after, before)
                    if mode == 'symlink': self.assertEqual(target.read_bytes(), b'untouched')

    def test_existing_and_symlink_output_never_overwritten(self):
        output = self.output()
        with ExitStack() as stack:
            self.forbid_research(stack)
            preparer.prepare(output)
            saved = {str(p.relative_to(output)):p.read_bytes() for p in output.rglob('*') if p.is_file()}
            with self.assertRaises((ValueError, FileExistsError, OSError)): preparer.prepare(output)
            self.assertEqual(saved, {str(p.relative_to(output)):p.read_bytes() for p in output.rglob('*') if p.is_file()})
            with tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary); marker = target / 'untouched'; marker.write_bytes(b'original')
                link = self.output(); link.symlink_to(target, target_is_directory=True)
                try:
                    with self.assertRaises((ValueError, OSError)): preparer.prepare(link)
                    with self.assertRaises((ValueError, OSError)): preparer.verify(link)
                    self.assertEqual(marker.read_bytes(), b'original')
                    self.assertEqual({p.name for p in target.iterdir()}, {'untouched'})
                finally:
                    link.unlink()


if __name__ == '__main__':
    unittest.main()
