"""Inspect pinned public author workbooks offline; never fit or execute formulas."""
import argparse
import json
from pathlib import Path
import sys

from autoresearch.chemotopo_data import inspect_chemotopo
from autoresearch.contracts import ResearchError


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        result = inspect_chemotopo(args.directory)
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=False)
        (output/'qualification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        print(json.dumps({'ok': True, 'output': str(output.absolute()), 'qualification': result['qualification'],
                          'join': result['join'], 'issues': result['issues'], 'model_fits': 0, 'model_calls': 0}, ensure_ascii=False, indent=2))
        return 0
    except (ResearchError, OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': {'code': getattr(error,'code','INSPECTION_UNAVAILABLE'),
                          'message': str(error) if isinstance(error,ResearchError) else 'Source or fresh output is unavailable.'}}, ensure_ascii=False))
        return 1


if __name__ == '__main__': raise SystemExit(main())
