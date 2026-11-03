"""Explicitly dispose an old unknown wait, then use at most one original slot."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autoresearch.contracts import ResearchError
from autoresearch.local_ollama import file_info, require
from autoresearch.source_assessment_continuation import SourceAssessmentContinuation


def compact(value):
    result = {k: value[k] for k in ('status', 'disposition_sha256', 'source_snapshot_sha256',
              'budget', 'unknown_outcome_preserved', 'automatic_retry', 'scientific_validation',
              'task_complete', 'new_fits') if k in value}
    outcome = value.get('new_outcome')
    if outcome:
        action = outcome.get('action')
        result['outcome'] = {'status': outcome['status'], 'error_code': outcome['error_code'],
                             'action': action['action'] if action else None,
                             'action_id': action['id'] if action else None,
                             'snapshot_sha256': outcome['snapshot_sha256']}
        if action and action['action'] == 'record_assessment':
            result['outcome']['answer_statuses'] = [{k: answer[k] for k in ('question_id', 'status')}
                                                    for answer in action['parameters']['answers']]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['dispose', 'status', 'resume'])
    parser.add_argument('--workflow', required=True)
    parser.add_argument('--reason')
    parser.add_argument('--max-new-requests', type=int, default=0, choices=[0, 1])
    parser.add_argument('--unknown-receipt')
    parser.add_argument('--model-store')
    parser.add_argument('--transport-output')
    parser.add_argument('--port', type=int, default=11448)
    parser.add_argument('--ollama-executable', default=str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Ollama/ollama.exe'))
    args = parser.parse_args()
    try:
        continuation = SourceAssessmentContinuation(args.workflow)
        if args.action == 'dispose':
            require(args.reason and args.max_new_requests == 0, 'INVALID_REQUEST', 'Disposition needs a reason and performs no model call.')
            continuation.dispose(actor='operator_assistant', reason=args.reason, reasoning_profile='low')
            result = continuation.status()
        elif args.action == 'status':
            require(args.max_new_requests == 0, 'INVALID_REQUEST', 'Status never sends requests.')
            result = continuation.status()
        elif args.max_new_requests == 0:
            result = continuation.advance(max_new_requests=0)
        else:
            current = continuation.status()
            if current['status'] != 'ready':
                # Captured response recovery or terminal readback never starts a server.
                result = continuation.advance(max_new_requests=0)
            else:
                require(args.unknown_receipt and args.model_store, 'INVALID_REQUEST', 'Exact old unknown receipt and existing model store required.')
                from autoresearch.source_continuation_transport import OwnedContinuationOllama
                digest, _, _ = file_info(Path(args.unknown_receipt).absolute(), 2 * 1024 * 1024)
                output = Path(args.transport_output).absolute() if args.transport_output else continuation.root / 'history' / 'continuation-transport-000001'
                cache = output.with_name(output.name + '-cache')
                with OwnedContinuationOllama(args.ollama_executable, cache, output,
                        model_store=args.model_store, port=args.port,
                        original_identity=current['profile']['model_identity'],
                        unknown_receipt=args.unknown_receipt, unknown_sha256=digest) as client:
                    result = continuation.advance(client=client, max_new_requests=1)
                result['transport_cleanup'] = {'owned_server_stopped': client.stopped,
                                                'key_metadata_unchanged': client.key_metadata_unchanged}
                print(json.dumps({'transport_cleanup': result['transport_cleanup']}, ensure_ascii=False))
        print(json.dumps(compact(result), ensure_ascii=False))
        outcome = result.get('new_outcome')
        return 1 if result['status'] == 'needs_attention' or (outcome and outcome['status'] == 'invalid') else 0
    except (ResearchError, OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'code': getattr(error, 'code', 'CONTINUATION_FAILED'),
                          'automatic_retry': False, 'new_fits': 0}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
