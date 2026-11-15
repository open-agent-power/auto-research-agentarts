"""Bounded retrospective paired accounting; never execute or change a study.

Requires the original continuation source pins and the frozen S060 protocol.
This is a trusted-local developer audit, not a new research tool or inference.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

EPSILON = 1e-12


def sign(value):
    return 1 if value > EPSILON else -1 if value < -EPSILON else 0


def summarize_pairs(rows, saved):
    """All pairs, with full precision and no assumption of query independence."""
    if len(rows) != 100 or len({row['query_id'] for row in rows}) != 100:
        raise ValueError('Exactly100 distinct original query pairs are required.')
    rows = sorted(rows, key=lambda row: row['query_id'])
    for row in rows:
        if any(type(row[key]) not in (int, float) or not math.isfinite(row[key])
               or not 0 <= row[key] <= 1 for key in ('baseline', 'candidate')):
            raise ValueError('Only original finite metric values in[0,1] are accepted.')
    deltas = [row['candidate'] - row['baseline'] for row in rows]
    mean = math.fsum(deltas) / len(deltas)
    counts = {'wins': sum(sign(d) == 1 for d in deltas),
              'losses': sum(sign(d) == -1 for d in deltas),
              'ties': sum(sign(d) == 0 for d in deltas)}
    if (any(saved.get(k) != v for k, v in counts.items())
            or type(saved.get('mean')) not in (int, float)
            or not math.isclose(mean, saved['mean'], abs_tol=EPSILON, rel_tol=0)):
        raise ValueError('Saved full-precision paired summary differs from all query pairs.')
    influence = []
    for i, row in enumerate(rows):
        loo = math.fsum(deltas[:i] + deltas[i+1:]) / (len(deltas) - 1)
        influence.append({**row, 'query_id_sha256': hashlib.sha256(row['query_id'].encode()).hexdigest(),
                          'delta': deltas[i], 'leave_one_out_mean': loo})
    values = [r['leave_one_out_mean'] for r in influence]
    original_sign = sign(mean)
    aggregate = {'queries': len(rows), 'direction': 'tfidf_cosine_minus_bm25', 'epsilon': EPSILON,
                 'saved_mean': saved['mean'], 'checked_fsum_mean': mean, **counts,
                 'leave_one_out_min': min(values), 'leave_one_out_max': max(values),
                 'min_excluded_query_sha256': [r['query_id_sha256'] for r in influence if r['leave_one_out_mean'] == min(values)],
                 'max_excluded_query_sha256': [r['query_id_sha256'] for r in influence if r['leave_one_out_mean'] == max(values)],
                 'leave_one_out_sign_counts': {'positive': sum(sign(v) == 1 for v in values),
                    'negative': sum(sign(v) == -1 for v in values), 'near_zero': sum(sign(v) == 0 for v in values)},
                 'original_mean_sign_under_epsilon': original_sign,
                 'leave_one_out_near_zero_count': sum(sign(v) == 0 for v in values) if original_sign else None,
                 'leave_one_out_opposite_sign_count': sum(sign(v) == -original_sign for v in values) if original_sign else None,
                 'near_zero_and_opposite_counts_applicable': bool(original_sign)}
    return {'aggregate': aggregate, 'per_query': influence}


def inventory(root):
    # Integrity hashing outside the analysis guard reads private-marked bytes.
    return {str(p.relative_to(root)): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
            for p in root.rglob('*') if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='New developer evidence JSON file; must not already exist.')
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Preserve the existing audit; do not overwrite it.')
    # Prevent reading stale pyc before importing the pinned product.
    sys.pycache_prefix = tempfile.mkdtemp(prefix='s060-clean-import-')
    sys.dont_write_bytecode = True
    from autoresearch import staged_feedback_reader as reader, staged_relevance_adapter as staged
    from autoresearch import retrieval_holdout as holdout, retrieval_lexical as lexical
    from autoresearch import relevance_retrieval_adapter as relevance, host_model_selection as host
    from autoresearch.local_workbench import LocalWorkbench
    from autoresearch.project_controller import ProjectController
    from autoresearch.research_project import ResearchProject, code_identity
    from autoresearch.contracts import fingerprint
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    repo = Path(__file__).resolve().parents[1]
    protocol_path = repo / 'docs/execution/g5-local/saved-validation-stability-protocol-v1.json'
    protocol = json.loads(protocol_path.read_text())
    baseline_path = repo / 'runs/s059-verification/protected-before.json'
    assert hashlib.sha256(baseline_path.read_bytes()).hexdigest() == protocol['case_inventory_manifest_sha256']
    baseline = json.loads(baseline_path.read_text())
    assert code_identity() == protocol['reader_core']
    assert protocol['metrics'] == ['recall@20', 'mrr@10'] and protocol['epsilon'] == EPSILON
    assert protocol['expected_queries_per_case'] == 100 and len(protocol['cases']) == 2
    result = {'schema_version': 'saved-validation-stability-audit-v1',
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'protocol_sha256': hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
              'reader_core': code_identity(), 'cases': [], 'scope': protocol['scope'],
              'bounds': protocol['bounds'], 'limitations': protocol['limitations']}
    for case_spec in protocol['cases']:
        case = repo.parent / 'source-pins' / case_spec['relative_path']
        before_files = inventory(case)
        assert before_files == baseline[case_spec['label']]
        if case_spec['project_relative_path']:
            project = ResearchProject(case / case_spec['project_relative_path'])
        else:
            manager = LocalWorkbench.open_readonly(case / 'manager')
            with manager._connect(readonly=True) as con:
                _, project = manager._project(con, case_spec['project_id'])
        state = project.status()
        assert state['id'] == case_spec['project_id'] and state['code_identity'] == case_spec['producer_core']
        assert state['source_snapshot_sha256'] == case_spec['source_snapshot_sha256']
        assert state['budget']['local_tool_calls_used'] == state['budget']['local_tool_call_limit'] == 3
        actions = [a for a in state['actions'] if a['command'] == staged.TOOL_ID]
        assert len(actions) == 1
        action = actions[0]
        primary_path = project.root / action['artifact']
        private = [case / 'private', project.root / 'private_evaluation', project.root / 'host-model-selections']
        real_open, real_os_open = Path.open, os.open
        def check(path):
            if isinstance(path, int): return
            path = Path(os.fsdecode(path)).absolute()
            assert not any(path == p or path.is_relative_to(p) for p in private), 'private path access'
            if path.is_relative_to(project.root / 'artifacts'):
                assert path == primary_path, 'non-primary artifact access'
        def path_open(path, *a, **kw):
            check(path)
            return real_open(path, *a, **kw)
        def os_open(path, *a, **kw):
            check(path)
            return real_os_open(path, *a, **kw)
        def no(*a, **kw): raise AssertionError('No new compute, dispatch, write, Host or recovery')
        metrics = {}
        with ExitStack() as guards:
            guards.enter_context(patch.object(Path, 'open', path_open))
            guards.enter_context(patch.object(os, 'open', os_open))
            for obj, name in ((holdout, '_verified_private'), (staged, 'execute'),
                (lexical, 'build_index'), (lexical, 'retrieve'), (lexical, 'metrics'), (relevance, 'retrieve'),
                (ResearchProject, 'step'), (ResearchProject, 'resume'), (ResearchProject, '_recover'),
                (ResearchProject, '_writer'), (ProjectController, 'advance_selection'),
                (host.HostModelSelection, 'prepare'), (host.HostModelSelection, 'request'),
                (host, 'run_claude_selection'), (Ridge, 'fit'), (StandardScaler, 'fit')):
                guards.enter_context(patch.object(obj, name, side_effect=no))
            with patch.object(reader, '_checked_primary', wraps=reader._checked_primary) as calls:
                checked = reader._checked_primary(project, state, action)
                assert calls.call_count == 1
            qids = sorted(checked['source']['spec']['query_splits']['validation'])
            assert len(qids) == len(set(qids)) == 100
            assert {qid for split, qid, method in checked['metrics'] if split == 'validation'} == set(qids)
            for metric in protocol['metrics']:
                rows = [{'query_id': qid,
                         'baseline': checked['metrics'][('validation', qid, 'bm25')]['metrics'][metric],
                         'candidate': checked['metrics'][('validation', qid, 'tfidf_cosine')]['metrics'][metric]}
                        for qid in qids]
                saved = checked['summary']['splits']['validation']['paired_candidate_minus_baseline'][metric]
                metrics[metric] = summarize_pairs(rows, saved)
            assert project.status() == state
        after_files = inventory(case)
        assert before_files == after_files
        result['cases'].append({'label': case_spec['label'], 'project_id': state['id'], 'run_id': state['run_id'],
            'producer_core': state['code_identity'], 'source_snapshot_sha256': state['source_snapshot_sha256'],
            'primary_action_id': action['id'], 'primary_result_sha256': action['result_sha256'],
            'checked_primary_calls': 1, 'unchanged_files': len(after_files),
            'source_inventory_sha256': fingerprint(before_files), 'state_sha256': fingerprint(state),
            'budget': state['budget'], 'metrics': metrics})
    result['guard_scope'] = protocol['guard_scope']
    result['actual_counts'] = {'cases': 2, 'paired_differences': 400, 'leave_one_out_means': 400,
                              'new_research_actions': 0, 'new_models': 0, 'new_fits': 0,
                              'new_index_rank_score_calls': 0, 'development_tokens': 'unknown', 'development_cost': 'unknown'}
    with args.output.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps({'status': 'passed', 'output': str(args.output),
          'output_sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
          'cases': [{k: c[k] for k in ('label', 'unchanged_files', 'checked_primary_calls')} for c in result['cases']]}, indent=2))


if __name__ == '__main__':
    main()
