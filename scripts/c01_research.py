"""Operator-selected paths; research actions arrive as bounded UTF-8 JSON on stdin."""
import argparse
import json
from pathlib import Path
import sys

from autoresearch.c01_research import C01Research
from autoresearch.contracts import ResearchError


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdin.reconfigure(encoding='utf-8', errors='strict')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['create', 'observe', 'apply', 'export'])
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--archive')
    parser.add_argument('--index')
    parser.add_argument('--goal')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--max-actions', type=int, default=12)
    parser.add_argument('--max-fits', type=int, default=4)
    args = parser.parse_args()
    study = C01Research(args.workspace)
    try:
        if args.command == 'create':
            if not all((args.archive, args.index, args.goal)):
                parser.error('create requires --archive, --index and --goal')
            result = study.create(args.archive, args.index, args.goal, max_actions=args.max_actions, max_fits=args.max_fits)
        elif args.command == 'apply':
            raw = sys.stdin.buffer.read(32769)
            if len(raw) > 32768:
                raise ValueError('oversized research request')
            result = study.apply(json.loads(raw.decode('utf-8-sig')))
        elif args.command == 'observe':
            result = study.observe()
        else:
            if args.output is None or args.output.exists():
                parser.error('export requires a new --output directory')
            result = study.export()
            args.output.mkdir(parents=True)
            (args.output / 'research.json').write_text(json.dumps(result['state'], ensure_ascii=False, indent=2), encoding='utf-8')
            (args.output / 'research.md').write_text(result['markdown'], encoding='utf-8')
            (args.output / 'reproduction.json').write_text(json.dumps(result['reproduction'], ensure_ascii=False, indent=2), encoding='utf-8')
            result = {'output': str(args.output.resolve()), 'status': result['state']['status']}
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False, indent=2))
        return 0
    except (ResearchError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': {'code': getattr(error, 'code', 'INVALID_REQUEST'), 'message': str(error)}}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
