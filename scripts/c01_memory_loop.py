"""Operator-only entry for bounded C01 decisions with exact-scope numerical memory."""
import argparse
import json
import sqlite3
import sys

from autoresearch.c01_memory_loop import C01MemoryLoop
from autoresearch.contracts import ResearchError
from c01_model_loop import load_config


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['configure', 'run', 'status', 'reconcile'])
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--memory-workspace')
    parser.add_argument('--config')
    parser.add_argument('--max-requests', type=int, default=8)
    parser.add_argument('--max-cost-cny', default='5')
    parser.add_argument('--max-new-requests', type=int, default=8)
    parser.add_argument('--allow-live', action='store_true', help='Does not enable real endpoints')
    parser.add_argument('--call-id')
    parser.add_argument('--confirm-worker-stopped', action='store_true')
    args = parser.parse_args()
    try:
        runner = C01MemoryLoop(args.workspace)
        if args.command == 'configure':
            if not args.memory_workspace or not args.config: parser.error('configure requires memory-workspace and config')
            result = runner.configure(load_config(args.config), memory_workspace=args.memory_workspace,
                                      max_requests=args.max_requests, max_cost_cny=args.max_cost_cny)
        elif args.command == 'run':
            result = runner.run(load_config(args.config) if args.config else None,
                                max_new_requests=args.max_new_requests, allow_live=args.allow_live)
        elif args.command == 'reconcile':
            if not args.call_id: parser.error('reconcile requires call-id')
            result = runner.reconcile(args.call_id, confirm_worker_stopped=args.confirm_worker_stopped)
        else: result = runner.status()
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False, allow_nan=False, indent=2))
        return 0
    except (ResearchError, ValueError, OSError, sqlite3.Error) as error:
        print(json.dumps({'ok': False, 'error': {'code': getattr(error, 'code', 'MEMORY_UNAVAILABLE'),
              'message': str(error) if isinstance(error, ResearchError) else 'Memory or local controller state is unavailable.'}}, ensure_ascii=False))
        return 1


if __name__ == '__main__': raise SystemExit(main())
