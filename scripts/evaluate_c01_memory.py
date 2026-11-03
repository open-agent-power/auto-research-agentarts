"""Paired public-data mechanism check. The decision service is explicitly scripted.

No real LLM, provider, cloud endpoint or scientific novelty claim is involved.
Run only with operator-selected paths; output must be a fresh directory.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from autoresearch.c01_memory_context import MemoryContext, scope_for_study
from autoresearch.c01_memory_loop import adapter_identity
from autoresearch.c01_research import C01Research, code_identity
from autoresearch.c01_research_outputs import public_record
from autoresearch.c01_research_verifier import validate_record
from autoresearch.contracts import canonical, fingerprint
from autoresearch.research_memory import ResearchMemory
import c01_model_fixture as fixture


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')


def recipe_key(recipe):
    return fingerprint({'alpha': float(recipe['alpha']), 'features': sorted(recipe['features'])})


def policy(context):
    """One registered policy for every arm: first unobserved recipe among 1 and100.

    Deliberate dependence on the supplied context tests wiring, not intelligence.
    All other decisions use the existing fixture's actual current feedback.
    """
    chosen = fixture.decision(context)
    if chosen['action'] == 'fit':
        seen = {recipe_key(item['payload']['recipe'])
                for item in context.get('conditional_memory', {}).get('entries', [])
                if item['kind'] == 'fit_observation'}
        for alpha in (1.0, 100.0):
            candidate = {**chosen['parameters'], 'alpha': alpha}
            if recipe_key(candidate) not in seen:
                chosen['parameters'] = candidate
                chosen['reason'] = 'FIXTURE registered first-unseen recipe policy; historical context is advisory, not validation.'
                break
    return chosen


def cli(script, command, workspace, environment, directory, label, *arguments):
    completed = subprocess.run([sys.executable, '-B', str(script), command, '--workspace', str(workspace), *arguments],
                               env=environment, capture_output=True, text=True, encoding='utf-8', timeout=120)
    (directory / (label + '.stderr.txt')).write_text(completed.stderr, encoding='utf-8')
    reply = json.loads(completed.stdout)
    write(directory / (label + '.json'), reply)
    if completed.returncode or reply.get('ok') is not True:
        raise RuntimeError('Local fixture CLI failed; retain its evidence: ' + label)
    return reply['result']


def evaluate(args):
    root = Path(__file__).resolve().parents[1]
    output = Path(args.output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    source = C01Research(args.seed_study)
    seed = source.export()
    research = public_record(seed['state'])
    write(output / 'seed-public-research.json', research)
    write(output / 'seed-reproduction.json', seed['reproduction'])
    prior = {recipe_key(item['recipe']) for item in research['fits']}
    if len(prior) != 1 or float(research['fits'][0]['recipe']['alpha']) != 1:
        raise ValueError('This registered mechanism comparison requires one prior alpha1 recipe')
    memory = ResearchMemory(output / 'mechanism-fixture-memory')
    imported = memory.import_study(research, seed['reproduction'])
    write(output / 'memory-import.json', imported)
    write(output / 'pre-registration.json', {
        'schema_version': 'c01-memory-mechanism-evaluation-v1', 'decision_service': 'operator_scripted_fixture_not_llm',
        'policy': 'first recipe absent from supplied active fit memory among alpha1 then alpha100; otherwise existing fixture policy',
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'adapter_sha256': adapter_identity(), 'analysis_code_sha256': code_identity(),
        'seed_observation_sha256': seed['state']['observation_sha256'], 'scope': imported['scope'],
        'prior_recipe_keys': sorted(prior), 'primary_measure': 'duplicate vs new recipe relative to registered prior history',
        'prior_history_boundary': 'Only the registered R22 seed is supplied. Alpha100 was also evaluated in older R18; it is not project-level novelty.',
        'not_measured': ['LLM strategy gain', 'scientific gain', 'reduced total fitting', 'new independent data'],
        'arms': ['no_memory', 'active_exact_memory', 'retired_fit_control', 'mismatched_scope_control'],
        'same_per_arm': {'max_fits': 1, 'max_actions': 8, 'max_requests': 8, 'virtual_cost_cap_cny': '5',
                         'goal': 'Controlled memory mechanism: one recipe and real diagnostics, then stop'},
        'actual_cloud_calls': 0, 'actual_model_calls': 0, 'actual_cost_cny': 0})
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(root / 'src')
    environment[fixture.KEY_ENV] = fixture.FIXTURE_KEY
    summary = []
    fit_id = next(item['record']['id'] for item in MemoryContext(memory.root).snapshot(source)['entries']
                  if item['record']['kind'] == 'fit_observation')
    mismatch = Path(args.mismatched_memory).absolute()
    mismatch_before = hashlib.sha256((mismatch / 'memory.sqlite').read_bytes()).hexdigest()
    for arm in ('no_memory', 'active_exact_memory', 'retired_fit_control', 'mismatched_scope_control'):
        directory = output / arm
        directory.mkdir()
        if arm == 'retired_fit_control':
            write(directory / 'withdrawal.json', memory.set_status(fit_id, 'retired',
                  'Controlled mechanism comparison: exclude the prior fit, not a scientific judgement.', 'evaluation-retire-fit'))
        selected_memory = mismatch if arm == 'mismatched_scope_control' else memory.root
        study = C01Research(directory / 'study')
        study.create(args.archive, args.index, 'Controlled memory mechanism: one recipe and real diagnostics, then stop',
                     max_actions=8, max_fits=1)
        scope = scope_for_study(study)
        if scope != imported['scope']: raise RuntimeError('Actual case and historical numerical conditions differ')
        if arm != 'no_memory':
            recalled = MemoryContext(selected_memory).snapshot(study)
            write(directory / 'eligible-before.json', recalled)
            if arm == 'mismatched_scope_control' and recalled['entries']:
                raise RuntimeError('Expected the old evaluator scope to return zero entries; do not relabel it')
        script = root / 'scripts' / ('c01_model_loop.py' if arm == 'no_memory' else 'c01_memory_loop.py')
        with fixture.model_fixture(policy=policy) as (endpoint, records):
            config = directory / 'fixture-config.json'
            write(config, fixture.configuration(endpoint))
            extra = [] if arm == 'no_memory' else ['--memory-workspace', str(selected_memory)]
            cli(script, 'configure', study.root, environment, directory, 'configure', '--config', str(config),
                '--max-requests', '8', '--max-cost-cny', '5', *extra)
            partial = cli(script, 'run', study.root, environment, directory, 'process-one', '--max-new-requests', '2')
            if partial['budget']['requests_reserved'] != 2: raise RuntimeError('First process did not stop at its bound')
            final = cli(script, 'run', study.root, environment, directory, 'process-two', '--max-new-requests', '6')
            write(directory / 'http-records.json', records)
        exported = study.export()
        record = public_record(exported['state'])
        write(directory / 'public-research.json', record)
        write(directory / 'reproduction.json', exported['reproduction'])
        verification = validate_record(record, exported['reproduction'])
        write(directory / 'independent-verification.json', verification)
        fits = record['fits']
        if (len(records) != 5 or len(fits) != 1 or final['status'] != 'completed'
                or [item['action'] for item in exported['state']['actions']] != ['search', 'fit', 'residuals', 'correlation', 'stop']
                or any(call['status'] != 'applied' for call in final['calls'])):
            raise RuntimeError('Comparison arm did not complete the registered actual tool sequence')
        duplicate = sum(recipe_key(fit['recipe']) in prior for fit in fits)
        projected = [json.loads(row['payload']['messages'][-1]['content']).get('conditional_memory', {}).get('entries', [])
                     for row in records]
        row = {'arm': arm, 'alpha': fits[0]['recipe']['alpha'], 'duplicate_recipes': duplicate,
               'new_recipes_relative_to_prior': len(fits) - duplicate, 'recipe_fits': len(fits),
               'fold_fits': sum(action['result']['fold_fits'] for action in exported['state']['actions'] if action['action'] == 'fit'),
               'http_requests': len(records), 'memory_entries_sent_first_request': len(projected[0]),
               'scope_sha256': fingerprint(scope), 'input_sha256': exported['reproduction']['inputs_sha256'],
               'corpus_sha256': exported['state']['corpus_sha256'],
               'accounted_virtual_micros': final['budget']['accounted_or_reserved_micros'],
               'scientific_validation': False, 'live_llm_calls': 0, 'actual_cost_cny': 0}
        summary.append(row)
    if [row['alpha'] for row in summary] != [1.0, 100.0, 1.0, 1.0]:
        raise RuntimeError('Observed recipe choices do not match the registered mechanism and controls')
    if len({row['input_sha256'] for row in summary}) != 1 or len({row['corpus_sha256'] for row in summary}) != 1:
        raise RuntimeError('Comparison input or corpus changed')
    if hashlib.sha256((mismatch / 'memory.sqlite').read_bytes()).hexdigest() != mismatch_before:
        raise RuntimeError('Read-only mismatched memory control changed')
    result = {'schema_version': 'c01-memory-mechanism-result-v1', 'passed': True, 'arms': summary,
              'historical_acquisition_fold_fits': 32, 'source_import_independent_recomputation_fold_fits': 32,
              'new_experiment_fold_fits': sum(row['fold_fits'] for row in summary),
              'new_result_independent_recomputation_fold_fits': 128,
              'mismatched_memory_sha256_unchanged': mismatch_before,
              'actual_cost_cny': 0, 'cloud_calls': 0, 'live_llm_calls': 0,
              'conclusion': 'The registered scripted policy used active exact-scope context to select a recipe absent only from the supplied R22 seed history at the same fitting budget. Alpha100 was already evaluated in older R18; this is not project-level novelty. No reduction in total fitting or LLM/scientific benefit was demonstrated.'}
    write(output / 'result.json', result)
    with (output / 'comparison.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    (output / 'README.md').write_text(
        '# 条件记忆机制对照\n\n'
        '同一公开8合金输入、固定评价器、资料索引、行动工具、预算与脚本策略。'
        '每组从独立研究开始，经两个CLI进程完成检索、拟合、两项诊断与停止。\n\n'
        '| 条件 | alpha | 重复已知配方 | 相对历史的新配方 | 实际逐折拟合 |\n|---|---:|---:|---:|---:|\n'
        + ''.join(f"| {row['arm']} | {row['alpha']} | {row['duplicate_recipes']} | {row['new_recipes_relative_to_prior']} | {row['fold_fits']} |\n" for row in summary)
        + '\n匹配记忆使同一脚本选择另一项配方；撤回或版本不匹配时不会使用该配方记忆。'
        '这里的新旧仅相对提供的R22测试历史；alpha100在较早R18也试过，不是全项目新实验。'
        '总拟合数没有减少，历史获取与独立复算另计。策略明确由程序写定，不能证明LLM获得更好的研究策略，'
        '也不能把此重复数据分析解释为独立验证或新材料发现。\n\n'
        '原始请求、响应、收到的记忆、真实逐折预测与独立复算均保留在各条件目录。实际云端/模型调用和费用均为0。\n', encoding='utf-8')
    return {'output': str(output), **result}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'archive', 'index', 'seed-study', 'mismatched-memory'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args), ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
