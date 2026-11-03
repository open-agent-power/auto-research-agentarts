"""Seal a real evidence selection as a JSON and teammate Markdown handoff."""
import argparse
import json
from pathlib import Path

from autoresearch.chemotopo_experiment_evidence import _safe_file
from autoresearch.diagnostic_view import read_diagnostic_artifacts
from autoresearch.handoff_view import export_handoff


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--diagnostic-directory', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    directory = Path(args.diagnostic_directory).absolute()
    diagnostic = json.loads(_safe_file(directory / 'diagnostic.json', 3_000_000))
    read_diagnostic_artifacts(directory, {'snapshot_sha256': diagnostic['iteration_snapshot_sha256']})
    manifest = export_handoff(args.workspace, diagnostic, args.output)
    print(json.dumps({'ok': True, 'snapshot_sha256': manifest['snapshot_sha256'],
                      'diagnostic_snapshot_sha256': manifest['diagnostic_snapshot_sha256'],
                      'model_calls': 0, 'new_fits': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
