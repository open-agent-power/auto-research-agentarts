"""Scoped local research memory. Paths are operator-selected, never model commands."""
import argparse
import json
from pathlib import Path
import sys

from autoresearch.research_memory import ResearchMemory


def load(path):
    with Path(path).open('rb') as stream:
        data = stream.read(4*1024*1024+1)
    if len(data) > 4*1024*1024:
        raise ValueError('oversized memory input')
    def reject(_):
        raise ValueError('nonfinite JSON')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    return json.loads(data.decode('utf-8-sig'), parse_constant=reject, object_pairs_hook=unique)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['import', 'recall', 'retire', 'restore'])
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--research')
    parser.add_argument('--reproduction')
    parser.add_argument('--scope')
    parser.add_argument('--entry-id')
    parser.add_argument('--reason')
    parser.add_argument('--request-id')
    args = parser.parse_args()
    memory = ResearchMemory(args.workspace)
    if args.command == 'import':
        if not args.research or not args.reproduction:
            parser.error('import requires --research and --reproduction')
        result = memory.import_study(load(args.research), load(args.reproduction))
    elif args.command == 'recall':
        if not args.scope:
            parser.error('recall requires --scope JSON file')
        result = memory.recall(load(args.scope))
    else:
        if not all((args.entry_id, args.reason, args.request_id)):
            parser.error('inclusion change requires --entry-id, --reason and --request-id')
        result = memory.set_status(args.entry_id, 'retired' if args.command == 'retire' else 'active', args.reason, args.request_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
