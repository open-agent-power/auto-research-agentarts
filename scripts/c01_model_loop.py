"""Operator CLI for the local C01 model-fixture controller; live access is prohibited."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

from autoresearch.c01_model_loop import C01ModelLoop
from autoresearch.contracts import ResearchError


def load_config(path):
    with Path(path).open('rb') as stream: payload = stream.read(65537)
    if len(payload) > 65536: raise ValueError('oversized fixture configuration')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('duplicate configuration field')
            result[key] = value
        return result
    def invalid(_): raise ValueError('nonfinite configuration')
    return json.loads(payload.decode('utf-8-sig'), object_pairs_hook=unique, parse_constant=invalid)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['configure', 'run', 'status', 'reconcile'])
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--config')
    parser.add_argument('--max-requests', type=int, default=8)
    parser.add_argument('--max-cost-cny', default='5')
    parser.add_argument('--max-new-requests', type=int, default=8)
    parser.add_argument('--allow-live', action='store_true', help='Does not bypass the fixture-only gate')
    parser.add_argument('--call-id')
    parser.add_argument('--confirm-worker-stopped', action='store_true')
    args = parser.parse_args()
    try:
        runner = C01ModelLoop(args.workspace)
        if args.command == 'configure':
            if not args.config: parser.error('configure requires --config')
            result = runner.configure(load_config(args.config), max_requests=args.max_requests, max_cost_cny=args.max_cost_cny)
        elif args.command == 'run':
            result = runner.run(load_config(args.config) if args.config else None,
                                max_new_requests=args.max_new_requests, allow_live=args.allow_live)
        elif args.command == 'reconcile':
            if not args.call_id: parser.error('reconcile requires --call-id')
            result = runner.reconcile(args.call_id, confirm_worker_stopped=args.confirm_worker_stopped)
        else: result = runner.status()
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False, allow_nan=False, indent=2))
        return 0
    except (ResearchError, ValueError, OSError, sqlite3.Error) as error:
        code = error.code if isinstance(error, ResearchError) else 'INVALID_CONFIG_OR_LOCAL_STATE'
        print(json.dumps({'ok': False, 'error': {'code': code, 'message': str(error) if isinstance(error, ResearchError) else 'Fixture configuration or local state is unavailable.'}}, ensure_ascii=False))
        return 1


if __name__ == '__main__': raise SystemExit(main())
