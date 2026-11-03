"""Create editable evidence-return sheets, or compile them into a new receipt."""
import argparse
import json

from autoresearch.evidence_draft import prepare_draft, compile_draft


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    for name in ('prepare', 'compile'):
        mode = modes.add_parser(name)
        mode.add_argument('--handoff-directory', required=True)
        mode.add_argument('--diagnostic-directory', required=True)
        mode.add_argument('--output', required=True)
        if name == 'compile': mode.add_argument('--draft-directory', required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        result = prepare_draft(args.handoff_directory, args.diagnostic_directory, args.output)
        info = {**result, 'draft_created': True}
    else:
        result = compile_draft(args.draft_directory, args.handoff_directory, args.diagnostic_directory, args.output)
        info = {'snapshot_sha256': result['snapshot_sha256'], 'task_id': result['task_id'],
                'interpretation_status': result['interpretation_status'], 'scientific_validation': False,
                'locator_validation': 'provided_not_verified'}
    print(json.dumps({'ok': True, **info, 'model_calls': 0, 'new_fits': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
