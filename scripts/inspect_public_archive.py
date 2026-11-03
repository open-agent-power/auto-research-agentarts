"""Offline bounded inventory of a captured public ZIP; never extract or execute."""
import argparse
import json
from pathlib import Path
import sys

from autoresearch.archive_inventory import inspect_archive
from autoresearch.contracts import ResearchError


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--expected-md5')
    parser.add_argument('--preview-member')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        result = inspect_archive(args.archive, expected_sha256=args.expected_sha256,
                                 expected_md5=args.expected_md5, preview_member=args.preview_member)
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=False)
        (output / 'inventory.json').write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
        print(json.dumps({'ok': True, 'output': str(output.absolute()),
                         **{key: result[key] for key in ('archive_sha256', 'archive_bytes', 'member_count', 'candidate_extensions', 'scientific_candidate_files_not_samples')},
                         'scientific_validation': False, 'files_extracted': 0}, ensure_ascii=False, indent=2))
        return 0
    except (ResearchError, ValueError, OSError) as error:
        print(json.dumps({'ok': False, 'error': {'code': getattr(error, 'code', 'ARCHIVE_UNAVAILABLE'),
                         'message': str(error) if isinstance(error, ResearchError) else 'Captured archive or output is unavailable.'}}, ensure_ascii=False))
        return 1


if __name__ == '__main__': raise SystemExit(main())
