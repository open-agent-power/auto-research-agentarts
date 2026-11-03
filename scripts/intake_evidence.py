"""Receive a bound evidence draft once, then resume local preparation."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).absolute().parents[1] / 'src'))
from autoresearch.evidence_intake import EvidenceIntake
from autoresearch.contracts import ResearchError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    for name in ('start', 'resume', 'status'):
        mode = modes.add_parser(name); mode.add_argument('--workspace', required=True)
        if name != 'status': mode.add_argument('--stop-after', choices=('receipt', 'prepared'), default='prepared')
        if name == 'start':
            for arg in ('draft-directory', 'handoff-directory', 'diagnostic-directory'): mode.add_argument('--' + arg, required=True)
    args = parser.parse_args()
    try:
        intake = EvidenceIntake(args.workspace)
        if args.mode == 'start': intake.create(args.draft_directory, args.handoff_directory, args.diagnostic_directory)
        result = intake.status() if args.mode == 'status' else intake.advance(args.stop_after)
        print(json.dumps({'ok': result['status'] != 'needs_attention', **result}, ensure_ascii=False))
        return 1 if result['status'] == 'needs_attention' else 0
    except (ResearchError, OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'code': getattr(error, 'code', 'INTAKE_FAILED'), 'error': str(error)[:500],
                          'model_calls': 0, 'new_fits': 0, 'budget_created': False}, ensure_ascii=False))
        return 1


if __name__ == '__main__': raise SystemExit(main())
