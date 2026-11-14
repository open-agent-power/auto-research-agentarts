"""Read the fixed standalone scheduling study's saved reference."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autoresearch.saved_study_reference import read_saved_study_reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('summary', 'status'))
    parser.parse_args()
    result = read_saved_study_reference()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
