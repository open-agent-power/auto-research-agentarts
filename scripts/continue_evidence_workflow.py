"""Prepare or continue one frozen source assessment without replacing its budget."""
import argparse
import json
import os
from pathlib import Path

from autoresearch.contracts import ResearchError
from autoresearch.evidence_workflow import EvidenceWorkflow, _path
from autoresearch.local_ollama import require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workflow', required=True)
    parser.add_argument('--source-packet'); parser.add_argument('--goal')
    parser.add_argument('--max-requests', type=int)
    parser.add_argument('--prior-attempt'); parser.add_argument('--protocol-change-reason')
    parser.add_argument('--max-new-requests', type=int, default=0)
    parser.add_argument('--model-store'); parser.add_argument('--cache')
    parser.add_argument('--port', type=int, default=11448)
    parser.add_argument('--ollama-executable', default=str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Ollama/ollama.exe'))
    args = parser.parse_args()
    if not 0 <= args.max_new_requests <= 4 or (args.max_requests is not None and not 2 <= args.max_requests <= 4):
        parser.error('max-requests 2..4 and max-new-requests 0..4 required')
    try:
        workflow = EvidenceWorkflow(args.workflow)
        if not workflow.config_path.exists():
            require(bool(args.source_packet and args.goal and args.protocol_change_reason), 'INVALID_REQUEST',
                    'New workflow needs source-packet, goal and protocol-change-reason.')
            workflow.create(args.source_packet, args.goal, max_requests=args.max_requests or 4,
                            prior_attempt=args.prior_attempt, protocol_change_reason=args.protocol_change_reason)
        else:
            config = workflow._config()
            for argument, key in ((args.source_packet, 'source_packet'), (args.prior_attempt, 'prior_attempt')):
                require(argument is None or str(_path(argument)) == config[key], 'CONFIG_CHANGED', 'Frozen source/prior paths differ.')
            for argument, key in ((args.goal, 'goal'), (args.max_requests, 'max_requests'),
                                  (args.protocol_change_reason, 'protocol_change_reason')):
                require(argument is None or argument == config[key], 'CONFIG_CHANGED', 'Frozen goal, purpose or cumulative request cap differs.')

        def transport(directory):
            # Called only inside advance's single-writer lock, after recovery
            # established that a new native request is actually permitted.
            require(bool(args.model_store), 'INVALID_REQUEST', 'Live continuation requires the existing model store.')
            from autoresearch.reasoning_profile import OwnedHighReasoningOllama
            return OwnedHighReasoningOllama(args.ollama_executable, args.cache or workflow.root / 'model-cache',
                                            directory, port=args.port, model_store=args.model_store)

        result = workflow.advance(args.max_new_requests, transport=transport if args.max_new_requests else None)
        print(json.dumps({k: result[k] for k in ('workflow_status', 'study_status', 'controller_status',
                                                 'controller_reason', 'budget', 'publication', 'progress', 'attention_code',
                                                 'external_task_executed', 'scientific_validation', 'new_fits')}, ensure_ascii=False))
        return 1 if result['workflow_status'] == 'needs_attention' else 0
    except (ResearchError, OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'code': getattr(error, 'code', 'WORKFLOW_FAILED'),
                          'automatic_retry': False, 'new_fits': 0}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
