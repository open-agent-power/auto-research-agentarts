"""Prepare the bounded UCI Bike 2011 source from an already acquired local ZIP.

Source URL and acquisition time are operator declarations, not network provenance.
Failure leaves the uniquely claimed output directory and all saved files intact.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile

# Do not load a stale bytecode cache in place of the pinned adapter sources.
_bytecode_sandbox = tempfile.TemporaryDirectory(prefix='bike-source-pycache-')
sys.pycache_prefix = _bytecode_sandbox.name
sys.dont_write_bytecode = True
from autoresearch import tabular_quality_adapter as adapter

URL = 'https://archive.ics.uci.edu/static/public/275/bike+sharing+dataset.zip'
LICENSE_URL = 'https://creativecommons.org/licenses/by/4.0/'
MAX_ZIP = 4 * 1024 * 1024
MAX_README = 256 * 1024
COLUMNS = ('dteday', 'workingday', 'temp', 'cnt')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _no_symlink_ancestors(path):
    path = Path(path)
    require('..' not in path.parts, 'Parent traversal is not allowed')
    absolute = Path(os.path.abspath(path))
    for p in reversed(absolute.parent.parents):
        require(not p.is_symlink(), 'Symlinked path ancestor')
    require(not absolute.parent.is_symlink(), 'Symlinked path ancestor')
    return absolute


def _bounded_file(path, limit):
    path = _no_symlink_ancestors(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        st = os.fstat(fd)
        require(stat.S_ISREG(st.st_mode) and 0 < st.st_size <= limit, 'Input must be a bounded regular file')
        with os.fdopen(fd, 'rb', closefd=False) as f:
            raw = f.read(limit + 1)
        require(0 < len(raw) <= limit and len(raw) == st.st_size, 'Input size changed or exceeded limit')
        return raw
    finally:
        os.close(fd)


def _write(path, raw):
    with path.open('xb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _parse_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON member')
            result[key] = value
        return result
    def reject(value):
        raise ValueError('Nonfinite JSON value')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


def _directory(output):
    output = _no_symlink_ancestors(output)
    # Trusted local path: reject symlinks in existing ancestors and never reuse output.
    require(output.parent.is_dir(), 'Unsafe output parent')
    output.mkdir(mode=0o700)
    return output


def _members(raw):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            require(1 <= len(entries) <= 16, 'Invalid ZIP member count')
            names = set()
            for entry in entries:
                name = entry.filename
                require(name and name not in ('.', '..') and '/' not in name and '\\' not in name
                        and ':' not in name and not any(ord(c) < 32 for c in name), 'Unsafe ZIP path')
                require(name.casefold() not in names, 'Duplicate ZIP member')
                names.add(name.casefold())
                mode = entry.external_attr >> 16
                require(not entry.is_dir() and not stat.S_ISLNK(mode)
                        and (stat.S_IFMT(mode) in (0, stat.S_IFREG)), 'ZIP member must be regular')
                require(not entry.flag_bits & 1 and entry.file_size <= adapter.MAX_CSV_BYTES, 'Invalid ZIP member')
            require('day.csv' in names and 'readme.txt' in names, 'Required ZIP members absent')
            day = next(e for e in entries if e.filename == 'day.csv')
            readme = next(e for e in entries if e.filename.casefold() == 'readme.txt')
            require(day.file_size > 0 and 0 < readme.file_size <= MAX_README, 'Member size outside bound')
            return archive.read(day), archive.read(readme), readme.filename
    except (zipfile.BadZipFile, KeyError, RuntimeError, StopIteration, EOFError) as exc:
        raise ValueError('Invalid ZIP or required exact day.csv missing') from exc


def _check_readme(raw):
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeError as exc:
        raise ValueError('README encoding is unknown') from exc
    require('\x00' not in text and bool(text.strip()), 'Invalid README')
    # Absence of a license in the README is not a license verification. Stop on
    # explicit conflicting/unrecognized license lines; human review is still required.
    for line in text.splitlines():
        low = line.casefold()
        if ('all rights reserved' in low or 'noncommercial' in low or 'non-commercial' in low
                or 'no derivatives' in low or 'sharealike' in low
                or re.search(r'\bcc\s*[- ]?by\s*[- ]?(nc|sa|nd)\b', low)):
            raise ValueError('README contains a conflicting rights notice')
        if re.match(r'^\s*(?:licen[cs]e|licen[cs]ing)\s*:', low):
            declared = low.split(':', 1)[1].strip()
            require(bool(re.search(r'(?:cc\s*[- ]?by\s*[- ]?4(?:\.0)?|creativecommons\.org/licenses/by/4\.0)', declared)),
                    'README contains an unknown license declaration')


def _project(raw):
    try:
        text = raw.decode('utf-8-sig')
        reader = csv.reader(io.StringIO(text, newline=''), strict=True)
        header = next(reader)
        require(len(header) == len(set(header)) and all(header.count(c) == 1 for c in COLUMNS), 'Invalid CSV header')
        index = [header.index(c) for c in COLUMNS]
        rows = {}
        for row in reader:
            require(len(row) == len(header), 'Invalid CSV row width')
            values = [row[i] for i in index]
            date = values[0]
            require(bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', date)), 'Invalid date format')
            day = dt.date.fromisoformat(date)
            require(day.isoformat() == date, 'Noncanonical date')
            if day.year == 2011:
                require(date not in rows and values[1] in ('0', '1'), 'Duplicate date or invalid workingday')
                rows[date] = values
        wanted = [(dt.date(2011, 1, 1) + dt.timedelta(days=i)).isoformat() for i in range(365)]
        require(sorted(rows) == wanted, '2011 must contain exactly one row per day')
        counts = {key: sum(rows[d][1] == key for d in wanted) for key in ('0', '1')}
        require(min(counts.values()) >= 3, 'Each workingday group needs at least 3 rows')
        out = io.StringIO(newline='')
        writer = csv.writer(out, lineterminator='\n')
        writer.writerow(COLUMNS)
        writer.writerows(rows[d] for d in wanted)
        return out.getvalue().encode('utf-8'), counts
    except (UnicodeError, csv.Error, StopIteration, OverflowError) as exc:
        raise ValueError('Malformed source CSV') from exc


def _production_claim():
    # Load only the sibling driver from this source tree. The driver verifies the
    # unique published pin, the active lease and the global claim/claim-copy.
    path = Path(__file__).absolute().with_name('run_bike_2011_study.py')
    spec = importlib.util.spec_from_file_location('_bike_claim_driver', path)
    require(spec is not None and spec.loader is not None, 'Claim driver unavailable')
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    _no_symlink_ancestors(Path(driver.WORKSPACE) / 'claim-copy.json')
    _no_symlink_ancestors(driver.CLAIM)
    require(Path(driver.WORKSPACE).is_dir() and not Path(driver.WORKSPACE).is_symlink(), 'Unsafe claimed workspace')
    claim, _ = driver.checked_claim()
    identity = claim['identity']
    require(identity.get('preparation_sha256') == sha(Path(__file__).read_bytes()), 'Preparation script differs from claim')
    return Path(driver.WORKSPACE), identity


def _allowed_url(url):
    try:
        parts = urllib.parse.urlsplit(url)
        return (parts.scheme == 'https' and parts.hostname == 'archive.ics.uci.edu'
                and parts.port in (None, 443) and parts.username is None and parts.password is None
                and not parts.fragment)
    except ValueError:
        return False


class _OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require(_allowed_url(newurl), 'Redirect outside official HTTPS host')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def acquire():
    """One fixed official download, only after original claim; never retries."""
    workspace, identity = _production_claim()
    _write(workspace / 'source-acquisition-started.json', _json({
        'schema_version': 'bike-2011-source-acquisition-started-v1', 'source_url': URL,
        'commit': identity['commit'], 'script_sha256': identity['preparation_sha256'],
        'output': str(workspace / 'acquisition' / 'original.zip')}))
    directory = _directory(workspace / 'acquisition')
    destination = directory / 'original.zip'
    opener = urllib.request.build_opener(_OfficialRedirect())
    request = urllib.request.Request(URL, headers={'Accept-Encoding': 'identity', 'User-Agent': 'AutoResearch-source-preparation/1'})
    with destination.open('xb') as out:
        try:
            with opener.open(request, timeout=30) as response:
                final_url = response.geturl()
                require(_allowed_url(final_url), 'Final URL outside official HTTPS host')
                require(response.headers.get('Content-Encoding', 'identity').lower() == 'identity', 'Unexpected content encoding')
                declared = response.headers.get('Content-Length')
                if declared is not None:
                    require(declared.isdigit() and 0 < int(declared) <= MAX_ZIP, 'Declared ZIP size outside bound')
                digest, size = hashlib.sha256(), 0
                while True:
                    chunk = response.read(min(65536, MAX_ZIP + 1 - size))
                    if not chunk:
                        break
                    size += len(chunk)
                    require(size <= MAX_ZIP, 'Downloaded ZIP exceeds size limit')
                    out.write(chunk)
                    digest.update(chunk)
                require(size > 0 and (declared is None or size == int(declared)), 'Incomplete or empty download')
                acquired = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        finally:
            out.flush()
            os.fsync(out.fileno())
            fd = os.open(directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    current_workspace, current_identity = _production_claim()
    require(current_workspace == workspace and current_identity == identity, 'Claim or runtime identity changed during acquisition')
    saved_raw = _bounded_file(destination, MAX_ZIP)
    require(len(saved_raw) == size and sha(saved_raw) == digest.hexdigest(), 'Saved download differs from received bytes')
    receipt = {'schema_version': 'bike-2011-source-acquisition-v1', 'requested_url': URL, 'final_url': final_url,
               'acquired_at_utc': acquired, 'bytes': size, 'sha256': digest.hexdigest(),
               'commit': identity['commit'], 'script_sha256': identity['preparation_sha256'],
               'path': 'acquisition/original.zip', 'clock_status': 'local_clock_not_independently_verified',
               'started_sha256': sha((workspace / 'source-acquisition-started.json').read_bytes())}
    _write(directory / 'receipt.json', _json(receipt))
    return receipt


def _checked_acquisition(zip_path, workspace, identity, expected_zip_sha256, acquired_at_utc):
    require(Path(os.path.abspath(zip_path)) == workspace / 'acquisition' / 'original.zip', 'Use the original claimed acquisition path')
    started_raw = _bounded_file(workspace / 'source-acquisition-started.json', 16384)
    started = _parse_json(started_raw)
    require(started == {'schema_version': 'bike-2011-source-acquisition-started-v1', 'source_url': URL,
            'commit': identity['commit'], 'script_sha256': identity['preparation_sha256'],
            'output': str(workspace / 'acquisition' / 'original.zip')}, 'Acquisition marker differs from claim')
    receipt_raw = _bounded_file(workspace / 'acquisition' / 'receipt.json', 16384)
    receipt = _parse_json(receipt_raw)
    require(type(receipt) is dict and set(receipt) == {'schema_version', 'requested_url', 'final_url', 'acquired_at_utc',
            'bytes', 'sha256', 'commit', 'script_sha256', 'path', 'clock_status', 'started_sha256'}
            and receipt['schema_version'] == 'bike-2011-source-acquisition-v1' and receipt['requested_url'] == URL
            and _allowed_url(receipt['final_url']) and receipt['acquired_at_utc'] == acquired_at_utc
            and type(receipt['bytes']) is int and 0 < receipt['bytes'] <= MAX_ZIP
            and receipt['sha256'] == expected_zip_sha256 and receipt['commit'] == identity['commit']
            and receipt['script_sha256'] == identity['preparation_sha256']
            and receipt['path'] == 'acquisition/original.zip'
            and receipt['started_sha256'] == sha(started_raw)
            and receipt['clock_status'] == 'local_clock_not_independently_verified', 'Acquisition receipt differs from claim')
    return receipt, receipt_raw, started_raw


def prepare(zip_path, output_dir, *, expected_zip_sha256, acquired_at_utc):
    require(type(expected_zip_sha256) is str and re.fullmatch(r'[0-9a-f]{64}', expected_zip_sha256), 'Expected ZIP SHA-256 required')
    require(type(acquired_at_utc) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', acquired_at_utc), 'UTC acquisition timestamp required')
    dt.datetime.strptime(acquired_at_utc, '%Y-%m-%dT%H:%M:%SZ')
    # No source bytes or output are opened before the original global claim and
    # workspace copy pass the driver's checks. There is no CLI bypass.
    workspace, identity = _production_claim()
    require(Path(os.path.abspath(output_dir)) == workspace / 'source', 'Output must be the claimed workspace/source')
    acquisition, acquisition_receipt_raw, acquisition_started_raw = _checked_acquisition(zip_path, workspace, identity, expected_zip_sha256, acquired_at_utc)
    _write(workspace / 'source-preparation-started.json', _json({
        'schema_version': 'bike-2011-source-preparation-started-v1',
        'commit': identity['commit'], 'script_sha256': identity['preparation_sha256'],
        'expected_zip_sha256': expected_zip_sha256, 'acquired_at_utc': acquired_at_utc,
        'output': str(workspace / 'source')}))
    output = _directory(output_dir)
    try:
        raw = _bounded_file(zip_path, MAX_ZIP)
        _write(output / 'original.zip', raw)
        require(sha(raw) == expected_zip_sha256 and len(raw) == acquisition['bytes'], 'Original ZIP SHA or size mismatch')
        day, readme, original_readme_name = _members(raw)
        _write(output / 'day.csv', day)
        _write(output / 'README.txt', readme)
        _check_readme(readme)
        projection, counts = _project(day)
        development = output / 'development'
        development.mkdir(mode=0o700)
        _write(development / 'bike-2011.csv', projection)
        spec = {'schema_version': 'tabular-quality-spec-v1', 'file': 'bike-2011.csv',
                'dataset_label': 'UCI Bike Sharing 2011 daily projection', 'source_url': URL,
                'license_note': 'UCI page declares CC BY 4.0; original README and source rights require operator review.',
                'sample_unit': 'daily record; independence unverified', 'group_columns': ['workingday'],
                'key_columns': ['dteday'], 'numeric_columns': ['temp', 'cnt'], 'target_column': 'cnt',
                'target_unit': 'rentals per day', 'missing_tokens': [''], 'delimiter': ',',
                'provenance': {'origin_sha256': sha(day), 'description': 'Operator projection of original day.csv: four columns, 2011 dates, sorted; original strings preserved.'}}
        _write(development / 'spec.json', _json(spec))
        packet = adapter.capture_source(development)
        packet_raw = _json(packet)
        require(len(packet_raw) <= adapter.MAX_PACKET_BYTES, 'Source packet exceeds size limit')
        _write(output / 'source.json', packet_raw)
        paths = {'original_zip': 'original.zip', 'original_day': 'day.csv', 'original_readme': 'README.txt',
                 'projection': 'development/bike-2011.csv', 'spec': 'development/spec.json', 'packet': 'source.json'}
        files = {}
        for key, path in paths.items():
            data = (output / path).read_bytes()
            files[key] = {'path': path, 'bytes': len(data), 'sha256': sha(data)}
        current_workspace, current_identity = _production_claim()
        require(current_workspace == workspace and current_identity == identity, 'Claim or runtime identity changed during preparation')
        current_acquisition, current_receipt_raw, current_started_raw = _checked_acquisition(zip_path, workspace, identity, expected_zip_sha256, acquired_at_utc)
        require(current_acquisition == acquisition and current_receipt_raw == acquisition_receipt_raw
                and current_started_raw == acquisition_started_raw and _bounded_file(zip_path, MAX_ZIP) == raw,
                'Original acquisition changed during preparation')
        require(files['original_zip']['sha256'] == expected_zip_sha256 and files['original_day']['sha256'] == packet['spec']['provenance']['origin_sha256']
                and files['projection']['sha256'] == packet['source']['sha256'] and files['spec']['sha256'] == packet['spec_source']['sha256'], 'Saved identities differ')
        receipt = {'schema_version': 'bike-2011-source-preparation-v1', 'source_url': URL,
                   'acquired_at_utc': acquired_at_utc, 'provenance_status': 'official_https_acquisition_local_clock_not_independently_verified',
                   'preparation_identity': {'commit': identity['commit'], 'script_sha256': identity['preparation_sha256'],
                                            'python': sys.version, 'executable': str(Path(sys.executable).resolve())},
                   'acquisition_receipt_sha256': sha(acquisition_receipt_raw),
                   'files': files, 'source_snapshot_sha256': packet['snapshot_sha256'],
                   'selection': {'year': 2011, 'rows': 365, 'columns': list(COLUMNS), 'workingday_counts': counts},
                   'license': {'source': 'UCI page declares CC BY 4.0', 'license_url': LICENSE_URL,
                               'attribution': 'Hadi Fanaee-T; UCI Bike Sharing Dataset; DOI 10.24432/C5W894',
                               'original_readme_name': original_readme_name, 'review_status': 'operator_review_required'},
                   'read_boundary': 'Complete ZIP and day.csv including possible 2012 were read; 2011 projection is not blind.'}
        _write(output / 'receipt.json', _json(receipt))
        return receipt
    except Exception as exc:
        try:
            _write(output / 'failure.json', _json({'schema_version': 'bike-2011-source-preparation-failure-v1', 'error_type': type(exc).__name__, 'message': str(exc)[:500], 'retry': 'stop_do_not_overwrite'}))
        except OSError:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--acquire', action='store_true')
    group.add_argument('--prepare', action='store_true')
    parser.add_argument('--zip', dest='zip_path')
    parser.add_argument('--output')
    parser.add_argument('--expected-zip-sha256')
    parser.add_argument('--acquired-at-utc')
    args = parser.parse_args()
    if args.acquire:
        require(not any((args.zip_path, args.output, args.expected_zip_sha256, args.acquired_at_utc)), 'Acquisition uses fixed claim and URL only')
        receipt = acquire()
        print(json.dumps({'status': 'acquired', 'sha256': receipt['sha256'], 'bytes': receipt['bytes'], 'acquired_at_utc': receipt['acquired_at_utc']}))
        return
    require(all((args.zip_path, args.output, args.expected_zip_sha256, args.acquired_at_utc)), 'Preparation requires the original acquisition and its saved identity')
    receipt = prepare(args.zip_path, args.output, expected_zip_sha256=args.expected_zip_sha256, acquired_at_utc=args.acquired_at_utc)
    print(json.dumps({'status': 'prepared', 'receipt_sha256': sha((Path(args.output) / 'receipt.json').read_bytes()),
                      'source_snapshot_sha256': receipt['source_snapshot_sha256']}))


if __name__ == '__main__':
    main()
