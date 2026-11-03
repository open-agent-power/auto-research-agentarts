"""Receive a task-bound evidence package without approving its interpretation."""
import argparse
import json
from pathlib import Path

from autoresearch.chemotopo_experiment_evidence import _safe_file
from autoresearch.diagnostic_view import read_diagnostic_artifacts
from autoresearch.evidence_submission import create_submission, read_submission
from autoresearch.handoff_view import read_handoff_artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--handoff-directory', required=True)
    parser.add_argument('--diagnostic-directory', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--input-directory', help='Directory containing submission.json and declared sources')
    mode.add_argument('--submission-directory', help='Read an existing receipt without changing it')
    parser.add_argument('--output', help='New immutable receipt directory; only for an input package')
    args = parser.parse_args()
    if bool(args.input_directory) != bool(args.output):
        parser.error('--output is required only with --input-directory')
    if args.input_directory:
        receipt = create_submission(args.handoff_directory, args.diagnostic_directory,
                                    args.input_directory, args.output)
    else:
        directory = Path(args.diagnostic_directory).absolute()
        diagnostic = json.loads(_safe_file(directory / 'diagnostic.json', 3_000_000))
        read_diagnostic_artifacts(directory, {'snapshot_sha256': diagnostic['iteration_snapshot_sha256']})
        handoff = json.loads(read_handoff_artifacts(args.handoff_directory, diagnostic)['handoff.json'])
        receipt = read_submission(args.submission_directory, handoff)
    print(json.dumps({'ok': True, 'snapshot_sha256': receipt['snapshot_sha256'],
                      'task_id': receipt['task_id'], 'sources': len(receipt['sources']),
                      'findings': len(receipt['findings']),
                      'unresolved_questions': len(receipt['unresolved_questions']),
                      'interpretation_status': 'pending', 'model_calls': 0, 'new_fits': 0,
                      'scientific_validation': False, 'biological_endpoint_eligible': False},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
