"""Package already-downloaded UCI originals and receipts; never convert or research."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


REPO = Path(__file__).resolve().parents[1]
OLD = REPO / 'runs/sprint-005-delivery/native-cpu-reproduction-evidence.zip'
OLD_SHA = 'e320404532fe80fd085ec1dbe07cf6e1abda6d8212a00f8295baa3c9371a1a58'
OUT = REPO / 'runs/sprint-006-originals'
ROOTS = {
    'concrete': Path('/workspace/work/g0-data-research'),
    'real-estate': Path('/workspace/work/g3-data/real-estate'),
    'slump': Path('/workspace/work/g3-data/slump'),
}
FILES = {
    'concrete': ['concrete-compressive-strength.zip', 'data.csv', 'uci-concrete-api.json',
                 'uci-concrete-page.md', 'Concrete_Readme.txt', 'source-manifest.json',
                 'conversion-receipt.json', 'inputs/spec.json', 'inputs/concrete.csv'],
    'real-estate': ['official.zip', 'archive-originals/Real estate valuation data set.xlsx',
                    'official-data.csv', 'official-api.json', 'official-page.md',
                    'source-manifest.json', 'retrieval.json', 'conversion-receipt.json',
                    'column-mapping.json', 'field-dictionary.json',
                    'inputs/spec.json', 'inputs/real-estate.csv'],
    'slump': ['official.zip', 'archive-originals/slump_test.data',
              'archive-originals/slump_test.names', 'official-api.json', 'official-page.md',
              'source-manifest.json', 'retrieval.json', 'conversion-receipt.json',
              'column-mapping.json', 'field-dictionary.json', 'inputs/spec.json', 'inputs/slump.csv'],
}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def source_bytes(entry: dict) -> bytes:
    path = Path(entry['source_path'])
    assert not path.is_symlink() and path.is_file()
    if entry.get('source_member'):
        with zipfile.ZipFile(path) as archive:
            return archive.read(entry['source_member'])
    return path.read_bytes()


def save_new(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def old_identity() -> dict:
    raw = OLD.read_bytes()
    assert len(raw) == 77407847 and digest(raw) == OLD_SHA
    return {'path': str(OLD), 'bytes': len(raw), 'sha256': digest(raw)}


def prepare() -> None:
    assert not OUT.exists(), 'Preserve existing supplement attempt'
    original = old_identity()
    entries, datasets = [], []
    with zipfile.ZipFile(OLD) as old:
        for name, root in ROOTS.items():
            manifest = json.loads((root / 'source-manifest.json').read_text())
            declared = {row.get('path', row.get('name')): row for row in manifest['files']}
            # Validate all old declarations, even intentionally omitted nonessential captures.
            for relative, expected in declared.items():
                path = root / relative
                assert not path.is_symlink()
                raw = path.read_bytes()
                assert len(raw) == expected['bytes'] and digest(raw) == expected['sha256']
            receipt = json.loads((root / 'conversion-receipt.json').read_text())
            raw_name = 'data.csv' if name == 'concrete' else (
                'official-data.csv' if name == 'real-estate' else 'archive-originals/slump_test.data')
            derived = root / f'inputs/{name}.csv'
            input_sha = receipt.get('input_sha256', receipt.get('original_sha256'))
            output_sha = receipt.get('output_sha256', receipt.get('derived_sha256'))
            assert digest((root / raw_name).read_bytes()) == input_sha
            assert digest(derived.read_bytes()) == output_sha
            assert digest((root / 'inputs/spec.json').read_bytes()) == receipt['spec_sha256']
            case_prefix = ('repo/runs/cloud-concrete-local-20261113-01/manager/inputs/'
                           if name == 'concrete' else
                           f'repo/runs/g3-local-transfer-20261113-01/{name}/manager/inputs/')
            matches = [item for item in old.namelist()
                       if item.startswith(case_prefix) and item.endswith(f'/{name}.csv')]
            assert len(matches) == 1 and digest(old.read(matches[0])) == output_sha
            for relative in FILES[name]:
                path = root / relative
                raw = path.read_bytes()
                entries.append({'path': f'originals/{name}/{relative}', 'source_path': str(path),
                                'bytes': len(raw), 'sha256': digest(raw),
                                'matches_old_source_manifest': relative in declared})
            datasets.append({'dataset': name, 'license_declaration': manifest['license'],
                             'license_source': manifest['license_source'],
                             'old_declared_files_verified': len(declared),
                             'source_manifest_sha256': digest((root / 'source-manifest.json').read_bytes()),
                             'original_used_for_conversion': raw_name, 'conversion_input_sha256': input_sha,
                             'conversion_receipt_sha256': digest((root / 'conversion-receipt.json').read_bytes()),
                             'saved_case_csv_member': matches[0], 'saved_case_csv_sha256': output_sha,
                             'excel_was_training_input': False})
    # Exact extraction from the pinned old download; member hash is observed now, not a prior receipt.
    concrete_zip = ROOTS['concrete'] / 'concrete-compressive-strength.zip'
    with zipfile.ZipFile(concrete_zip) as archive:
        raw = archive.read('Concrete_Data.xls')
    entries.append({'path': 'originals/concrete/archive-originals/Concrete_Data.xls',
                    'source_path': str(concrete_zip), 'source_member': 'Concrete_Data.xls',
                    'bytes': len(raw), 'sha256': digest(raw),
                    'identity_basis': 'Exact member of ZIP matched to old source-manifest; member SHA observed now'})
    assert len({row['path'] for row in entries}) == len(entries)
    OUT.mkdir(parents=True)
    plan = {'schema_version': 'uci-originals-supplement-v1', 'status': 'prepared_not_created',
            'parent_archive': original, 'host_packer_sha256': digest(Path(__file__).read_bytes()),
            'datasets': datasets, 'files': entries,
            'omissions': 'No Firecrawl request/index IDs, HTML duplicates, preparation logs, venv/cache, model or credentials.',
            'boundary': 'Old downloads and conversion receipts only; no network, conversion, fit, prediction or budget change.',
            'original_case_declarations_rewritten': False}
    save_new(OUT / 'supplement-manifest.json', plan)
    assert old_identity() == original
    print(json.dumps({'manifest': str(OUT / 'supplement-manifest.json'), 'files': len(entries),
                      'manifest_sha256': digest((OUT / 'supplement-manifest.json').read_bytes())}))


def create() -> None:
    path = OUT / 'supplement-manifest.json'
    plan = json.loads(path.read_text())
    assert plan['status'] == 'prepared_not_created'
    assert plan['host_packer_sha256'] == digest(Path(__file__).read_bytes())
    assert old_identity() == plan['parent_archive']
    destination = OUT / 'uci-original-downloads-supplement.zip'
    readme = ("UCI original-download supplement; parent native archive remains unchanged.\n"
              f"Parent SHA256: {OLD_SHA}\n"
              "Original official CSV/.data files, downloaded ZIP/Excel members, license notices and receipts are retained.\n"
              "Research conversion actually used official CSV (Concrete/Real Estate) or slump_test.data, not Excel.\n"
              "No preparation script or research is executed. Old absolute declarations are not rewritten.\n"
              "CC BY 4.0 declarations and original copyright/attribution notices remain in supplied originals.\n"
              "This supplement creates no new product/code license, legal assurance or dependency mirror.\n")
    with zipfile.ZipFile(destination, mode='x', compression=zipfile.ZIP_DEFLATED) as archive:
        for entry in plan['files']:
            raw = source_bytes(entry)
            assert len(raw) == entry['bytes'] and digest(raw) == entry['sha256']
            archive.writestr(entry['path'], raw)
        archive.writestr('supplement-manifest.json', path.read_bytes())
        archive.writestr('README.txt', readme)
        archive.writestr('archive_original_data_supplement.py', Path(__file__).read_bytes())
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(plan['files']) + 3
        for entry in plan['files']:
            raw = archive.read(entry['path'])
            assert len(raw) == entry['bytes'] and digest(raw) == entry['sha256']
    for entry in plan['files']:
        assert digest(source_bytes(entry)) == entry['sha256']
    assert old_identity() == plan['parent_archive']
    receipt = {'schema_version': 'uci-originals-supplement-create-v1', 'status': 'created_and_verified',
               'archive': str(destination), 'archive_bytes': destination.stat().st_size,
               'archive_sha256': digest(destination.read_bytes()),
               'manifest_sha256': digest(path.read_bytes()), 'source_files_unchanged': True,
               'parent_archive_unchanged': True, 'zip_crc_and_all_payload_sha256_passed': True,
               'members': len(plan['files']) + 3, 'network_downloads': 0,
               'new_conversion_fit_prediction_model_calls': 0, 'research_budget_mutations': 0}
    save_new(OUT / 'create-receipt.json', receipt)
    print(json.dumps(receipt))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['prepare', 'create'])
    args = parser.parse_args()
    prepare() if args.operation == 'prepare' else create()
