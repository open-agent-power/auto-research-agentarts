"""Export read-only postrun records bound to an existing sealed iteration."""
import argparse
import json
from pathlib import Path

from autoresearch.chemotopo_experiment_evidence import _safe_file
from autoresearch.chemotopo_iteration_report import read_iteration_artifacts
from autoresearch.postrun_view import export_postrun


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--iteration-directory', required=True)
    parser.add_argument('--assessment')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(args.iteration_directory).absolute(); target = Path(args.output).absolute()
    if target == root or target.is_relative_to(root) or root.is_relative_to(target):
        parser.error('Output must be separate from sealed iteration')
    iteration = json.loads(_safe_file(root / 'iteration.json', 3_000_000))
    read_iteration_artifacts(root, iteration)
    annotation = json.loads(_safe_file(Path(args.assessment), 10_000)) if args.assessment else None
    manifest = export_postrun(args.workspace, iteration, target, annotation)
    print(json.dumps({'ok': True, 'snapshot_sha256': manifest['snapshot_sha256'], 'new_fits': 0, 'new_model_calls': 0}))


if __name__ == '__main__':
    main()
