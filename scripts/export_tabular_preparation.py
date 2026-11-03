"""Seal an already prepared tabular evidence packet for read-only display."""
import argparse
import json

from autoresearch.tabular_preparation_view import export_tabular_preparation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation-directory', required=True)
    parser.add_argument('--handoff-directory', required=True)
    parser.add_argument('--diagnostic-directory', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = export_tabular_preparation(args.preparation_directory, args.handoff_directory,
                                         args.diagnostic_directory, args.output)
    print(json.dumps({'ok': True, **result}, ensure_ascii=False))


if __name__ == '__main__':
    main()
