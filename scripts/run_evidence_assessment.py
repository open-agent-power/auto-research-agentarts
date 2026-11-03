"""Read a returned evidence package and assess its remaining gaps in a fixed budget."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from autoresearch.contracts import ResearchError
from autoresearch.evidence_assessment import EvidenceAssessmentCloudLoop
from autoresearch.local_ollama import require
from autoresearch.reasoning_profile import OwnedHighReasoningOllama
from run_evidence_handoff import write, overlaps


def export_assessment(output, state):
    selected = next((a for a in reversed(state.get('actions', []))
                     if a['action'] == 'record_assessment'), None)
    if selected is None:
        return
    write(output / 'assessment.json', {
        'schema_version': 'p02-returned-evidence-assessment-export-v1',
        'source_snapshot_sha256': state['source_snapshot_sha256'],
        'action_id': selected['id'], 'answers': selected['parameters']['answers'],
        'model_reason_unreviewed': selected['reason'], 'interpretation_status': 'unreviewed',
        'scientific_validation': False, 'biological_endpoint_eligible': False,
    })
    lines = ['# 回传资料的模型判断', '',
             '以下是模型实际提交的判断，附已读取的来源片段 ID。收到资料和保存判断均不等于作者确认或科学验证。',
             '', '来源包：`' + state['source_snapshot_sha256'] + '`', '']
    for answer in selected['parameters']['answers']:
        lines += ['## ' + answer['question_id'], '', '模型分类：' + answer['status'], '',
                  answer['answer'], '', '所引片段：' + '、'.join(answer['evidence_ids']), '']
    lines += ['## 原始理由（未审定）', '', selected['reason'], '',
              '仍保留先前任务和提交记录；本次没有新拟合、原始图像重分析或生物终点放行。', '']
    with (output / 'assessment.md').open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--output', required=True)
    for name in ('handoff-directory', 'diagnostic-directory', 'submission-directory', 'goal'):
        parser.add_argument('--' + name)
    parser.add_argument('--max-requests', type=int)
    parser.add_argument('--max-new-requests', type=int, default=0)
    parser.add_argument('--model-store')
    parser.add_argument('--cache')
    parser.add_argument('--port', type=int, default=11448)
    parser.add_argument('--ollama-executable', default=str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Ollama/ollama.exe'))
    args = parser.parse_args()
    if not 0 <= args.max_new_requests <= 4 or (args.max_requests is not None and not 2 <= args.max_requests <= 4):
        parser.error('max-requests 2..4 and max-new-requests 0..4 required')
    workspace = Path(args.workspace).absolute()
    output = Path(args.output).absolute()
    for part in (output, *output.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            parser.error('receipt output cannot redirect')
    loop = EvidenceAssessmentCloudLoop(workspace)
    previous = None
    protected = [workspace]
    if loop.study.db.exists():
        with loop.study._connect() as con:
            previous, _, _ = loop.study._state(con)
        protected.extend(Path(v).absolute() for v in previous['private_sources'].values())
    sources = {k: getattr(args, k) for k in ('handoff_directory', 'diagnostic_directory', 'submission_directory')}
    protected.extend(Path(v).absolute() for v in sources.values() if v)
    if any(overlaps(output, p) for p in protected):
        parser.error('output must be separate from study and sources')
    output.mkdir(parents=True, exist_ok=False)
    server = None
    try:
        if previous is None:
            require(all(sources.values()) and bool(args.goal), 'INVALID_REQUEST', 'New assessment requires a bound returned submission and goal.')
            loop.study.create(**sources, goal=args.goal, max_requests=args.max_requests or 4)
        else:
            for key, value in sources.items():
                require(value is None or str(Path(value).absolute()) == previous['private_sources'][key], 'CONFIG_CHANGED', 'Source paths are frozen.')
            require(args.goal is None or args.goal == previous['goal'], 'CONFIG_CHANGED', 'Goal is frozen.')
            require(args.max_requests is None or args.max_requests == previous['max_requests'], 'CONFIG_CHANGED', 'Cumulative budget is frozen.')
        if args.max_new_requests == 0:
            state = loop.study.observe()
            write(output / 'study.json', state)
            export_assessment(output, state)
            if loop.db.exists():
                write(output / 'result.json', loop.status())
            print(json.dumps({'ok': True, 'study_status': state['status'], 'new_cloud_requests': 0, 'new_fits': 0}))
            return 0
        if loop.db.exists():
            recovered = loop.run(max_new_requests=0)
            write(output / 'before.json', recovered)
            if recovered['status'] != 'active':
                write(output / 'result.json', recovered)
                export_assessment(output, recovered['study'])
                print(json.dumps({'ok': True, 'status': recovered['status'], 'new_cloud_requests': 0, 'new_fits': 0}))
                return 0
        require(bool(args.model_store), 'INVALID_REQUEST', 'Live inference requires the existing model store.')
        with OwnedHighReasoningOllama(args.ollama_executable, args.cache or output / 'model-cache',
                                     output / 'transport', port=args.port, model_store=args.model_store) as server:
            write(output / 'server-identity.json', server.identity)
            identity = server.acquire()
            write(output / 'model-and-account-scope.json', identity)
            if not loop.db.exists():
                loop.configure(identity)
            before = loop.status()
            write(output / 'before-live.json', before)
            result = loop.run(server, max_new_requests=args.max_new_requests, verified_weights=identity)
            write(output / 'result.json', result)
        write(output / 'cleanup.json', {'owned_server_stopped': server.stopped, 'key_metadata_unchanged': server.key_metadata_unchanged})
        export_assessment(output, result['study'])
        print(json.dumps({'ok': True, 'status': result['status'], 'study_status': result['study']['status'],
                          'requests_reserved': result['budget']['requests_reserved'],
                          'new_cloud_requests': result['budget']['requests_reserved'] - before['budget']['requests_reserved'], 'new_fits': 0}))
        return 0
    except (ResearchError, OSError, ValueError, sqlite3.Error, UnicodeError, RecursionError) as error:
        receipt = {'ok': False, 'code': getattr(error, 'code', 'EVIDENCE_ASSESSMENT_FAILED'), 'error_class': type(error).__name__,
                   'automatic_retry': False, 'owned_server_stopped': getattr(server, 'stopped', False),
                   'key_metadata_unchanged': getattr(server, 'key_metadata_unchanged', None)}
        write(output / 'failure.json', receipt)
        print(json.dumps(receipt))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
