#!/usr/bin/env python3
"""Prepare and recheck one built-in synthetic hourly fixture; no external input.

This is not a real UCI parser, legal review, authorization or Project dispatch
mechanism. Private byte helpers are provided only for isolated synthetic tests.
"""
import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from autoresearch import tabular_quality_adapter as tabular
from autoresearch.contracts import canonical, fingerprint
from scripts import synthetic_time_report as checker

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / 'runs'
PREFIX = 's134-synthetic-time-'
CONFIG = {'schema_version':'synthetic-hourly-clock-v1', 'station':checker.STATION, 'clock':checker.CLOCK,
          'start':'2024-02-28T22:00:00', 'end_exclusive':'2024-03-01T02:00:00', 'step_hours':1,
          'row_order':'strict_ascending', 'missing_tokens':['','NA'], 'numeric_lexical_rule':'nonnegative_ascii_integer_only'}


def _check_config():
    if (CONFIG != {'schema_version':'synthetic-hourly-clock-v1', 'station':'SYNTHETIC_S1',
                   'clock':'synthetic_naive_clock_no_timezone_no_dst', 'start':'2024-02-28T22:00:00',
                   'end_exclusive':'2024-03-01T02:00:00', 'step_hours':1, 'row_order':'strict_ascending',
                   'missing_tokens':['','NA'], 'numeric_lexical_rule':'nonnegative_ascii_integer_only'}
            or checker.STATION != CONFIG['station'] or checker.CLOCK != CONFIG['clock']
            or checker.START != dt.datetime(2024,2,28,22) or checker.END != dt.datetime(2024,3,1,2)):
        raise ValueError('fixed synthetic clock configuration changed')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _bytes(value):
    return canonical(value).encode('utf-8')


def _fixture():
    """Construct all input bytes internally; no caller-supplied source is accepted."""
    rows = [','.join(checker.HEADER)]
    cursor = checker.START
    for index in range(28):
        x = 'NA' if index == 4 else str(index)
        outcome = '' if index == 9 else str(index * 2)
        rows.append(f'{checker.STATION},{cursor.year:04d},{cursor.month:02d},{cursor.day:02d},{cursor.hour:02d},{x},{outcome}')
        cursor += dt.timedelta(hours=1)
    if cursor != checker.END:
        raise ValueError('synthetic fixture window changed')
    csv_raw = ('\n'.join(rows) + '\n').encode('ascii')
    spec = {'schema_version':'tabular-quality-spec-v1', 'file':'source.csv',
            'dataset_label':'Invented 28-hour synthetic clock fixture',
            'source_url':'urn:autoresearch:synthetic-time-s134',
            'license_note':'Invented fixture only; not external source permission.',
            'sample_unit':'one invented synthetic clock hour', 'group_columns':[],
            'key_columns':['station','year','month','day','hour'], 'numeric_columns':['x','outcome'],
            'target_column':'outcome', 'target_unit':'synthetic unit', 'missing_tokens':['','NA'], 'delimiter':',',
            'provenance':{'origin_sha256':_sha(csv_raw), 'description':'Internally invented S134 synthetic fixture only.'}}
    return csv_raw, _bytes(spec)


def _inspect_csv(raw):
    return checker._inspect_csv(raw)


def _path(output_dir, *, existing):
    path = Path(output_dir).absolute()
    if path.parent != RUNS or not path.name.startswith(PREFIX) or path.name == PREFIX:
        raise ValueError('use a synthetic output directly under runs')
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('symbolic link in synthetic output path')
    if existing:
        if not path.is_dir(): raise ValueError('original synthetic output is unavailable')
    elif path.exists():
        raise ValueError('synthetic output already exists')
    return path


def _read_bounded(path, maximum):
    for part in (path, *path.parents):
        if part.is_symlink(): raise ValueError('symbolic link in synthetic input path')
    fd = os.open(path, os.O_RDONLY | getattr(os,'O_NOFOLLOW',0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
            raise ValueError('synthetic input size or type changed')
        chunks=[];remaining=maximum+1
        while remaining:
            block=os.read(fd,min(65536,remaining))
            if not block: break
            chunks.append(block);remaining-=len(block)
        after=os.fstat(fd);current=os.stat(path,follow_symlinks=False)
        identity=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        if identity(before)!=identity(after) or identity(before)!=identity(current):
            raise ValueError('synthetic input changed during read')
        raw=b''.join(chunks)
        if len(raw)!=before.st_size: raise ValueError('synthetic input was truncated')
        return raw
    finally:
        os.close(fd)


def _read_exact(path, expected):
    if _read_bounded(path, len(expected)) != expected:
        raise ValueError('synthetic original bytes changed')


def _write(path, raw):
    with path.open('xb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())


def _sync_directory(path):
    fd=os.open(path, os.O_RDONLY | getattr(os,'O_DIRECTORY',0))
    try: os.fsync(fd)
    finally: os.close(fd)


def _require_files(path, expected):
    with os.scandir(path) as iterator:
        entries = list(iterator)
    if {entry.name for entry in entries} != set(expected) or any(
            entry.is_symlink() or not entry.is_file(follow_symlinks=False) for entry in entries):
        raise ValueError('synthetic output file set changed')


def _identities():
    generator = Path(__file__).read_bytes()
    recalculator = Path(checker.__file__).read_bytes()
    return {'generator_sha256':_sha(generator), 'recalculator_sha256':_sha(recalculator),
            'tabular_identity':tabular.code_identity()}


def _report(csv_raw, spec_raw, packet_raw, identities):
    packet = tabular.load_source(packet_raw)
    if packet_raw != _bytes(packet): raise ValueError('synthetic packet bytes are not canonical')
    if (base64.b64decode(packet['source']['bytes_base64'], validate=True) != csv_raw
            or base64.b64decode(packet['spec_source']['bytes_base64'], validate=True) != spec_raw):
        raise ValueError('synthetic packet does not contain the fixed fixture bytes')
    facts = checker._inspect_csv(csv_raw)
    return {'schema_version':'synthetic-time-report-v1', 'synthetic_only':True,
            'config':CONFIG, 'config_sha256':fingerprint(CONFIG),
            'csv_sha256':_sha(csv_raw), 'spec_sha256':_sha(spec_raw), 'packet_sha256':_sha(packet_raw),
            'source_snapshot_sha256':packet['snapshot_sha256'], 'scope_sha256':fingerprint(packet['scope']),
            **identities, 'facts':facts,
            'limitations':['Artificial naive clock only; no real site, timezone, DST or source licence is verified.',
                           'Identity binds current local files and bytes, not a signature or authenticated in-memory code.',
                           'This report is not a Project dispatch gate or scientific authorization.']}


def _receipt(claim_raw, csv_raw, spec_raw, packet_raw, report_raw, report, identities):
    return {'schema_version':'synthetic-time-preparation-v1', 'synthetic_only':True,
            'files':{'claim.json':_sha(claim_raw), 'source.csv':_sha(csv_raw), 'spec.json':_sha(spec_raw),
                     'source.json':_sha(packet_raw), 'report.json':_sha(report_raw)},
            'report_sha256':_sha(report_raw), 'packet_sha256':_sha(packet_raw),
            'source_snapshot_sha256':report['source_snapshot_sha256'], **identities,
            'research_dispatches':0, 'model_calls':0, 'fits':0,
            'verification':'synthetic_bytes_and_mechanical_recomputation_not_external_authentication'}


def prepare(output_dir):
    _check_config();output=_path(output_dir,existing=False);csv_raw,spec_raw=_fixture();identities=_identities()
    facts=checker._inspect_csv(csv_raw)
    if facts['rows'] != 28: raise ValueError('synthetic fixture is incomplete')
    claim_raw=_bytes({'schema_version':'synthetic-time-claim-v1','synthetic_only':True,
                      'csv_sha256':_sha(csv_raw),'spec_sha256':_sha(spec_raw),**identities})
    output.mkdir(mode=0o700,parents=False,exist_ok=False)
    _write(output/'claim.json',claim_raw);_write(output/'source.csv',csv_raw);_write(output/'spec.json',spec_raw)
    for name,raw in (('claim.json',claim_raw),('source.csv',csv_raw),('spec.json',spec_raw)):_read_exact(output/name,raw)
    packet_raw=_bytes(tabular.capture_source(output))
    report=_report(csv_raw,spec_raw,packet_raw,identities);report_raw=_bytes(report)
    _write(output/'source.json',packet_raw);_write(output/'report.json',report_raw)
    for name,raw in (('claim.json',claim_raw),('source.csv',csv_raw),('spec.json',spec_raw),('source.json',packet_raw),('report.json',report_raw)):_read_exact(output/name,raw)
    _require_files(output, ('claim.json','source.csv','spec.json','source.json','report.json'))
    if _identities()!=identities: raise ValueError('synthetic report producer changed')
    _sync_directory(output)
    for name,raw in (('claim.json',claim_raw),('source.csv',csv_raw),('spec.json',spec_raw),('source.json',packet_raw),('report.json',report_raw)):_read_exact(output/name,raw)
    _require_files(output, ('claim.json','source.csv','spec.json','source.json','report.json'))
    _check_config()
    if _identities()!=identities: raise ValueError('synthetic report producer changed before receipt')
    receipt=_receipt(claim_raw,csv_raw,spec_raw,packet_raw,report_raw,report,identities)
    _write(output/'receipt.json',_bytes(receipt));_require_files(output, ('claim.json','source.csv','spec.json','source.json','report.json','receipt.json'))
    _sync_directory(output);_sync_directory(RUNS)
    return receipt


def verify(output_dir):
    """Read original output and recompute the report from fixed synthetic bytes."""
    _check_config();output=_path(output_dir,existing=True);csv_expected,spec_expected=_fixture();identities=_identities()
    _require_files(output, ('claim.json','source.csv','spec.json','source.json','report.json','receipt.json'))
    csv_raw=_read_bounded(output/'source.csv',checker.MAX_CSV_BYTES)
    spec_raw=_read_bounded(output/'spec.json',tabular.MAX_SPEC_BYTES)
    if csv_raw!=csv_expected or spec_raw!=spec_expected: raise ValueError('not the original fixed synthetic fixture')
    packet_raw=_read_bounded(output/'source.json',tabular.MAX_PACKET_BYTES)
    claim_raw=_bytes({'schema_version':'synthetic-time-claim-v1','synthetic_only':True,
                      'csv_sha256':_sha(csv_raw),'spec_sha256':_sha(spec_raw),**identities})
    report=_report(csv_raw,spec_raw,packet_raw,identities);report_raw=_bytes(report)
    receipt=_receipt(claim_raw,csv_raw,spec_raw,packet_raw,report_raw,report,identities);receipt_raw=_bytes(receipt)
    for name,raw in (('claim.json',claim_raw),('source.csv',csv_raw),('spec.json',spec_raw),('source.json',packet_raw),('report.json',report_raw),('receipt.json',receipt_raw)):_read_exact(output/name,raw)
    _require_files(output, ('claim.json','source.csv','spec.json','source.json','report.json','receipt.json'))
    _check_config()
    if _identities()!=identities: raise ValueError('synthetic report producer changed during verification')
    return receipt


def main():
    parser=argparse.ArgumentParser(description='Prepare or recheck only the fixed S134 synthetic clock fixture.')
    parser.add_argument('command',choices=('prepare','verify'));parser.add_argument('--output',required=True)
    args=parser.parse_args();receipt=prepare(args.output) if args.command=='prepare' else verify(args.output)
    print(json.dumps({'schema_version':receipt['schema_version'],'synthetic_only':True,'packet_sha256':receipt['packet_sha256'],'report_sha256':receipt['report_sha256']},sort_keys=True))


if __name__=='__main__':main()
