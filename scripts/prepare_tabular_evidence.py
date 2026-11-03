"""Prepare submitted XLSX cells/text lines as source-bound derived evidence."""
import argparse
import json

from autoresearch.tabular_submission import prepare_tabular_submission


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--handoff-directory', required=True)
    parser.add_argument('--diagnostic-directory', required=True)
    parser.add_argument('--submission-directory', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = prepare_tabular_submission(args.handoff_directory, args.diagnostic_directory,
                                        args.submission_directory, args.output)
    print(json.dumps({'ok': True, **result}, ensure_ascii=False))


if __name__ == '__main__':
    main()
