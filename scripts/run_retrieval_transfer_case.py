#!/usr/bin/env python3
"""Freeze and run one reviewed independent retrieval transfer case via native APIs."""
import argparse
import base64
import csv
from contextlib import ExitStack
import hashlib
import io
import os
from pathlib import Path
import re
import subprocess
import sys

# Reuse host I/O and original evidence inventories, not the old case runner,
# source acceptance protocol, budgets or execution permissions.
import run_native_cpu_cases as host

REPO = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
PROTOCOL = REPO/'docs/execution/g5-local/retrieval-transfer-protocol.md'
PREPARER = REPO/'scripts/prepare_retrieval_transfer_source.py'
LIMITS = dict(host.LIMITS)
THREAD_ENV = host.THREAD_ENV
ALLOWANCE = {'local_tools': 2, 'fits': 0, 'models': 0, 'evidence_reads': 0}
SEED = 'arguana-transfer-v1'
RULE = 'sha256(seed+LF+query_id)_ascending_then_query_id'
METHOD = 'research.relevance-fixed-pair'
AUDIT = 'research.relevance-saved-error-audit'
BEIR_ARCHIVE = 'cfdf79adce27a401b3cd3ea267903134dbfab2c6afeb95d7fe5724a00bf7557b'
CORPUS_SHA = '0627982cec4ee896df6dc98604ef6b499c83fd87a19eaaeb3f23b88bbef6cbce'
QUERIES_SHA = 'f8b7c903f95d9a2d291de3915a8fac25085e9db679f19f59fea4145bfd1df618'
QRELS_SET_SHA = '8a2be6e0eb6f50bb648e88fbd14b5bbf6323ff88742cd5b4161f9c722dca59ca'
STUDY_ID = 'g5-arguana-source-arm-transfer-v1'
STUDY_CLAIM = REPO/'.agent/autonomy/studies'/ (STUDY_ID+'.json')
SOURCE_CASE = REPO/'runs/g5-native-cases-20261113-01/retrieval'
METRIC_POINTER = 'tool_result.result.paired_summary.splits.test.paired_candidate_minus_baseline.recall@20.mean'
BASELINE = REPO/'runs/sprint-010-start-20261114/protected-before.json'
BASELINE_TREES = REPO/'runs/sprint-010-start-20261114/path-sets-before.json'
require, sha, canonical, save, read, parse, git = (host.require, host.sha, host.canonical,
                                                host.save, host.read, host.parse, host.git)


def runtime():
    for key in THREAD_ENV:
        os.environ[key] = '1'
    sys.path.insert(0, str(REPO/'src'))
    from autoresearch import relevance_retrieval_adapter, retrieval_lexical
    from autoresearch import research_project, project_controller, local_workbench, method_registry
    return relevance_retrieval_adapter, retrieval_lexical, research_project, project_controller, local_workbench, method_registry


def disabled(modules):
    from unittest.mock import patch
    adapter, lexical, *_ = modules
    guard = ExitStack()
    def deny(*args, **kwargs):
        raise AssertionError('Research computation is forbidden in this phase')
    for module, names in ((lexical, ('tokens', 'build_index', 'retrieve', 'metrics')),
                          (adapter, ('execute', 'retrieve', '_retrieve'))):
        for name in names:
            if hasattr(module, name):
                guard.enter_context(patch.object(module, name, side_effect=deny))
    guard.enter_context(patch.object(adapter.time, 'perf_counter', side_effect=deny))
    return guard


def committed_identity(commit):
    require(type(commit) is str and re.fullmatch('[0-9a-f]{40}', commit)
            and git('rev-parse', 'HEAD') == commit, 'Use the current full reviewed commit')
    specific = [SCRIPT, PROTOCOL, PREPARER, Path(host.__file__).resolve()]
    subprocess.run(['git', 'diff', '--exit-code', commit, '--', 'src/autoresearch',
                    *[str(p.relative_to(REPO)) for p in specific]], cwd=REPO,
                   check=True, stdout=subprocess.DEVNULL, timeout=20)
    paths = sorted((REPO/'src/autoresearch').rglob('*.py')) + specific
    result = {}
    for path in paths:
        relative = str(path.relative_to(REPO))
        git('ls-files', '--error-unmatch', relative)
        raw = read(path)
        result[relative] = {'bytes': len(raw), 'sha256': sha(raw)}
    return result


def protected():
    original = parse(read(BASELINE))
    require(type(original) is dict and len(original) == 494,
            'The original 494-file inventory must remain available')
    current = host.identities([Path(name) for name in original])
    require(current == original, 'An original protected file changed')
    expected_trees = parse(read(BASELINE_TREES))
    require(set(expected_trees) == {str(REPO/name) for name in (
        'runs/cloud-concrete-local-20261113-01', 'runs/g3-local-transfer-20261113-01',
        'runs/g5-native-cases-20261113-01')}, 'Fixed original path-set roots changed')
    actual_trees = {}
    for name in expected_trees:
        tree = Path(name)
        require(tree.is_dir(), 'An original protected tree is missing')
        actual_trees[name] = sorted(str(p.relative_to(tree)) for p in tree.rglob('*') if p.is_file())
    require(actual_trees == expected_trees, 'An original complete file path set changed')
    return {'files': current, 'tree_path_sets': actual_trees,
            'inventory_sha256': sha(read(BASELINE)), 'tree_inventory_sha256': sha(read(BASELINE_TREES))}


def validate_output(path):
    root = Path(path).absolute()
    require('..' not in root.parts and root.parent == REPO/'runs'
            and re.fullmatch(r'g5-retrieval-transfer-[A-Za-z0-9][A-Za-z0-9_.-]{0,64}', root.name)
            and not any(p.is_symlink() for p in (root, *root.parents)),
            'Output must be a fresh regular runs/g5-retrieval-transfer-<unique> path')
    return root


def checked_policy(raw):
    policy = parse(raw)
    literals = {'schema_version': 'retrieval-transfer-policy-v1', 'baseline': 'bm25',
                'candidate': 'tfidf_cosine', 'negative_control': 'tfidf_cosine',
                'objective': 'recall@20', 'selection_rule': 'source_scifact_coverage_guard_v1',
                'selection_seed': SEED}
    require(type(policy) is dict and set(policy) == set(literals)|{'source_evidence','limitations'}
            and all(type(policy[k]) is str and policy[k] == v for k,v in literals.items()),
            'Use the exact frozen source-only arm-selection policy')
    evidence = policy['source_evidence']
    require(type(evidence) is dict and type(evidence.get('paired_source_recall20_candidate_minus_baseline')) in (int,float)
            and -1 <= evidence['paired_source_recall20_candidate_minus_baseline'] < 0
            and evidence.get('source_baseline') == 'tfidf_cosine' and evidence.get('source_candidate') == 'bm25',
            'Source coverage loss, not target metrics, must choose TF-IDF')
    for key in ('result_sha256','source_snapshot_sha256','producer_code_identity','saved_artifact_sha256'):
        require(type(evidence.get(key)) is str and re.fullmatch('[0-9a-f]{64}', evidence[key]),
                'Exact source evidence digest is required: '+key)
    for key in ('project_id','action_id','metric_pointer'):
        require(type(evidence.get(key)) is str and 0 < len(evidence[key]) <= 500,
                'Exact source evidence pointer is required: '+key)
    require(type(policy['limitations']) is list and 1 <= len(policy['limitations']) <= 30
            and all(type(s) is str and 0 < len(s) <= 2000 for s in policy['limitations']), 'Keep explicit policy limitations')
    source_evidence_check(evidence)
    return policy


def source_evidence_check(evidence):
    """Verify saved source bytes/identities and its exact metric, without scoring."""
    inventory = parse(read(BASELINE))
    status_path = SOURCE_CASE/'final-project-status.json'
    relocation_path = SOURCE_CASE/'project-relocation.json'
    for path in (status_path,relocation_path):
        require(str(path) in inventory and sha(read(path)) == inventory[str(path)]['sha256'],
                'Source case state/relocation must be original protected bytes')
    state,relocation = parse(read(status_path)),parse(read(relocation_path))
    require(state['id'] == relocation['project_id'] == evidence['project_id'], 'Source project identity differs')
    actions = [a for a in state['actions'] if a['id'] == evidence['action_id']
               and a['command'] == 'research.retrieval-fixed-pair' and a['status'] == 'completed']
    require(len(actions) == 1, 'Use the original completed source retrieval action')
    action = actions[0]
    path = Path(relocation['relocated_project_root'])/action['artifact']
    require(type(evidence.get('source_artifact_path')) is str
            and Path(evidence['source_artifact_path']) == path and path.is_relative_to(SOURCE_CASE)
            and str(path) in inventory, 'Use the exact protected original source artifact path')
    raw = read(path,4194304)
    envelope = parse(raw)
    require(sha(raw) == inventory[str(path)]['sha256'] == evidence['saved_artifact_sha256']
            and envelope['sha256'] == action['result_sha256'] == evidence['result_sha256']
            and envelope['sha256'] == sha(canonical({k:v for k,v in envelope.items() if k != 'sha256'}).encode('utf-8'))
            and envelope['action_id'] == action['id'] == evidence['action_id']
            and envelope['source_snapshot_sha256'] == state['source_snapshot_sha256'] == evidence['source_snapshot_sha256']
            and envelope['code_identity'] == action['code_identity'] == state['code_identity'] == evidence['producer_code_identity'],
            'Saved source artifact, envelope or producer identity differs')
    tool = envelope['tool_result']
    metric = tool['result']['paired_summary']['splits']['test']['paired_candidate_minus_baseline']['recall@20']['mean']
    require(tool['tool_id'] == 'research.retrieval-fixed-pair' and tool['status'] == 'completed'
            and evidence['metric_pointer'] == METRIC_POINTER
            and canonical(metric) == canonical(evidence['paired_source_recall20_candidate_minus_baseline'])
            and metric < 0, 'Source policy must cite the exact actual saved negative coverage result')


def source_check(packet, selection_raw, modules):
    adapter = modules[0]
    with disabled(modules):
        payload = adapter.load_source(packet)
    require(payload['task_kind'] == 'relevance_retrieval'
            and payload['scope']['contract'] == 'relevance-retrieval-fixed-pair-v1'
            and type(payload['scope']['document_count']) is int and payload['scope']['document_count'] == 8674
            and type(payload['scope']['query_count']) is int and payload['scope']['query_count'] == 1406,
            'This study uses the independent full ArguAna corpus/query originals')
    spec = payload['spec']
    require(spec['source_provenance']['selection_sha256'] == sha(selection_raw), 'Selection original SHA differs')
    require(payload['assets']['corpus']['sha256'] == CORPUS_SHA
            and payload['assets']['queries']['sha256'] == QUERIES_SHA, 'Use complete original BEIR corpus/query bytes')
    selection = parse(selection_raw)
    raw_queries = base64.b64decode(payload['assets']['queries']['bytes_base64'], validate=True)
    ids = [parse(line)['_id'] for line in raw_queries.split(b'\n') if line.strip()]
    require(len(ids) == len(set(ids)) == 1406, 'Full original unique query population is required')
    ordered = sorted(ids, key=lambda qid: (sha((SEED+'\n'+qid).encode('utf-8')), qid))
    expected = {'dev': ordered[:80], 'validation': ordered[80:160], 'test': ordered[160:460]}
    require(selection.get('schema_version') == 'retrieval-transfer-selection-v1'
            and selection.get('seed') == SEED and selection.get('rule') == RULE
            and selection.get('archive_sha256') == BEIR_ARCHIVE
            and selection.get('population_query_ids_sha256') == sha(canonical(sorted(ids)).encode('utf-8'))
            and canonical(selection.get('population_count')) == '1406'
            and canonical(selection.get('evaluated_count')) == '460'
            and canonical(selection.get('counts')) == canonical({'dev':80,'validation':80,'test':300})
            and canonical(selection.get('remainder_queries')) == '946'
            and canonical(selection.get('query_splits')) == canonical(expected)
            and canonical(spec['query_splits']) == canonical(expected),
            'Use the fixed pre-score hash-only 80/80/300 procedural selection')
    qrels, roles = [], {}
    for role,count in (('train_qrels',160),('test_qrels',1246)):
        raw = base64.b64decode(payload['assets'][role]['bytes_base64'],validate=True)
        records = list(csv.reader(io.StringIO(raw.decode('utf-8'),newline=''),delimiter='\t',strict=True))
        require(records[0] == ['query-id','corpus-id','score'] and len(records)-1 == count,
                'Keep the complete fixed original qrels partition')
        rows = records[1:]
        require(all(len(row) == 3 and row[2] == '1' for row in rows), 'All original ArguAna grades must remain one')
        roles[role] = {row[0] for row in rows}
        qrels.extend(rows)
    require(len(qrels) == len({row[0] for row in qrels}) == 1406
            and {row[0] for row in qrels} == set(ids)
            and roles['train_qrels'] == set(expected['dev']+expected['validation'])
            and roles['test_qrels'] == set(ids)-roles['train_qrels']
            and sha(canonical(sorted(qrels)).encode('utf-8')) == QRELS_SET_SHA,
            'Complete original qrels row-set/grade identity or procedural partition changed')
    return payload


def prepare(args):
    root = validate_output(args.output)
    require(not root.exists(), 'Existing evidence is never replaced')
    require(type(args.packet_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.packet_sha256), 'Exact packet SHA required')
    disk = host.disk_headroom(root)
    code = committed_identity(args.code_commit)
    packet, policy_raw, selection_raw = read(args.packet), read(args.policy,65536), read(args.selection,65536)
    require(sha(packet) == args.packet_sha256, 'Explicit source packet SHA differs')
    policy = checked_policy(policy_raw)
    modules = runtime()
    payload = source_check(packet, selection_raw, modules)
    protection = protected()
    root.mkdir()
    (root/'frozen').mkdir()
    for name, raw in (('source.json',packet), ('policy.json',policy_raw), ('selection.json',selection_raw)):
        with (root/'frozen'/name).open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    freeze = {'schema_version':'g5-retrieval-transfer-freeze-v1', 'output_root':str(root.resolve()),
        'code_commit':args.code_commit, 'code_files':code,
        'project_code_identity':modules[2].code_identity(), 'runtime_dependencies':modules[5].runtime_dependencies(),
        'packet_original_path':str(args.packet.absolute()), 'packet_sha256':sha(packet), 'packet_bytes':len(packet),
        'policy_original_path':str(args.policy.absolute()), 'policy_sha256':sha(policy_raw), 'policy':policy,
        'selection_original_path':str(args.selection.absolute()), 'selection_sha256':sha(selection_raw),
        'snapshot_sha256':payload['snapshot_sha256'], 'scope':payload['scope'], 'limits':LIMITS,
        'protected':protection, 'disk_preflight':disk, 'python_executable':str(Path(sys.executable).absolute()),
        'python_version':sys.version, 'allowance':ALLOWANCE,
        'study_id':STUDY_ID,'budget_ref':STUDY_ID,
        'known_results':'Source SciFact outcomes are known. Target labels are public and schema inspected; target rankings/metrics have not selected arms. Fixed TF-IDF negative control equals source-informed TF-IDF; no incremental memory benefit can be inferred.',
        'review_required':'Independent exact freeze/output/code/policy/selection approval before any target evaluation.'}
    save(root/'freeze.json',freeze)
    save(root/'preflight.json',{'status':'frozen_not_executed','freeze_sha256':sha(read(root/'freeze.json')),
        'research_actions':0,'fits':0,'models':0,'api_calls':0,'schema_only':True})
    print(canonical({'status':'frozen_not_executed','freeze_sha256':sha(read(root/'freeze.json'))}))


def frozen(root):
    validate_output(root)
    raw = read(root/'freeze.json')
    value = parse(raw)
    require(value['schema_version'] == 'g5-retrieval-transfer-freeze-v1'
            and value['output_root'] == str(root.resolve())
            and value['study_id'] == value['budget_ref'] == STUDY_ID
            and canonical(value['limits']) == canonical(LIMITS)
            and canonical(value['allowance']) == canonical(ALLOWANCE), 'Unsupported/copied freeze or altered limits')
    host.disk_headroom(root)
    require(value['python_executable'] == str(Path(sys.executable).absolute()) and value['python_version'] == sys.version,
            'Use the exact frozen interpreter')
    require(committed_identity(value['code_commit']) == value['code_files'], 'Frozen source changed')
    require(protected() == value['protected'], 'Protected originals/inventories changed')
    packet, policy_raw, selection_raw = (read(root/'frozen/source.json'), read(root/'frozen/policy.json',65536),
                                          read(root/'frozen/selection.json',65536))
    require(sha(packet) == value['packet_sha256'] and len(packet) == value['packet_bytes']
            and sha(policy_raw) == value['policy_sha256'] and sha(selection_raw) == value['selection_sha256'],
            'Frozen source, policy or selection bytes changed')
    require(canonical(checked_policy(policy_raw)) == canonical(value['policy']), 'Frozen policy fields changed')
    payload = source_check(packet,selection_raw,runtime())
    require(payload['snapshot_sha256'] == value['snapshot_sha256'] and canonical(payload['scope']) == canonical(value['scope']),
            'Frozen derived scope changed')
    return raw,value


def reviewed(root, freeze_raw, freeze, review_raw):
    review = parse(review_raw)
    require(type(review) is dict and set(review) == {'schema_version','status','freeze_sha256','code_commit',
                'output_root','policy_sha256','selection_sha256','reviewer','limitations'}
            and review['schema_version'] == 'g5-retrieval-transfer-review-v1' and review['status'] == 'approved'
            and review['freeze_sha256'] == sha(freeze_raw) and review['code_commit'] == freeze['code_commit']
            and review['output_root'] == str(root.resolve()) and review['policy_sha256'] == freeze['policy_sha256']
            and review['selection_sha256'] == freeze['selection_sha256']
            and type(review['reviewer']) is str and bool(review['reviewer'].strip())
            and type(review['limitations']) is list and bool(review['limitations']), 'Independent exact approval required')
    return review


def run(args):
    root = args.output.absolute()
    freeze_raw,freeze = frozen(root)
    review_raw = read(args.review,65536)
    reviewed(root,freeze_raw,freeze,review_raw)
    require(not (root/'attempt.json').exists(), 'Existing attempt must only recover original native requests; do not rerun batch')
    require(not any(path.is_symlink() for path in (STUDY_CLAIM,*STUDY_CLAIM.parents)), 'Study claim path must not redirect')
    STUDY_CLAIM.parent.mkdir(parents=True,exist_ok=True)
    save(STUDY_CLAIM,{'schema_version':'retrieval-transfer-study-claim-v1','study_id':STUDY_ID,
        'output_root':str(root.resolve()),'freeze_sha256':sha(freeze_raw),'policy_sha256':freeze['policy_sha256'],
        'selection_sha256':freeze['selection_sha256'],'review_sha256':sha(review_raw),'automatic_retry':False})
    with (root/'independent-review.json').open('xb') as stream:
        stream.write(review_raw); stream.flush(); os.fsync(stream.fileno())
    save(root/'attempt.json',{'schema_version':'g5-retrieval-transfer-attempt-v1','status':'running',
        'freeze_sha256':sha(freeze_raw),'review_sha256':sha(review_raw),'automatic_retry':False})
    command = [sys.executable,'-B',str(SCRIPT),'_worker','--output',str(root)]
    save(root/'subprocess-command.json',{'argv':command,'limits':LIMITS})
    env = {**os.environ, **{name:'1' for name in THREAD_ENV}, 'PYTHONDONTWRITEBYTECODE':'1'}
    try:
        with (root/'worker.stdout').open('xb') as out, (root/'worker.stderr').open('xb') as err:
            process = subprocess.run(command,cwd=REPO,env=env,stdout=out,stderr=err,
                                     timeout=LIMITS['wall_seconds'],check=False)
        complete = process.returncode == 0 and (root/'result.json').is_file()
        save(root/'attempt-final.json',{'status':'completed' if complete else 'unknown_preserve_no_retry',
            'returncode':process.returncode,'automatic_retry':False})
        require(complete,'Worker did not complete; preserve original native requests and never batch-retry')
    except subprocess.TimeoutExpired:
        save(root/'attempt-final.json',{'status':'unknown_wall_timeout','automatic_retry':False})
        raise
    print(canonical(parse(read(root/'result.json'))))


def policy_projection(tool, policy, source_action):
    # The negative control is an alias of the same saved TF-IDF values, not a
    # third ranking/scoring arm. This makes the zero incremental contrast exact.
    rows = []
    baseline = {(row['split'],row['query_id']):row['metrics']
                for row in tool['result']['per_query_metrics'] if row['method'] == policy['baseline']}
    for item in tool['result']['per_query_metrics']:
        if item['method'] == policy['candidate']:
            parent = baseline[(item['split'],item['query_id'])]
            rows.append({'split':item['split'],'query_id':item['query_id'],
                         'bm25_baseline':parent,'candidate':item['metrics'],
                         'fixed_tfidf_negative_control':item['metrics'],
                         'candidate_minus_baseline':{metric:item['metrics'][metric]-parent[metric]
                                                     for metric in item['metrics']},
                         'candidate_minus_negative_control':{metric:0.0 for metric in item['metrics']}})
    require(len(rows) == len(baseline) == 460, 'Complete paired saved metrics are required for the policy projection')
    objective_delta = tool['result']['paired_summary']['splits']['test']['paired_candidate_minus_baseline']['recall@20']['mean']
    conclusion = ('local_coverage_transfer_supported' if objective_delta > 1e-12 else
                  'negative_transfer' if objective_delta < -1e-12 else 'no_coverage_improvement')
    return {'schema_version':'saved-retrieval-policy-projection-v1','source_action':source_action,
            'policy':policy,'per_query_candidate_and_control':rows,
            'paired_summary':tool['result']['paired_summary'],
            'predeclared_objective_conclusion':{'objective':'test recall@20','candidate_minus_baseline':objective_delta,
                'rule':'delta>1e-12 supports local coverage transfer; abs(delta)<=1e-12 no improvement; delta<-1e-12 negative transfer',
                'conclusion':conclusion,'scope':'This procedural query subset only; no automatic promotion, significance or generality claim.',
                'hypothesis_test_performed':False},
            'candidate_equals_source_free_control':True,'incremental_memory_benefit':0.0,
            'interpretation':'Structural equality of fixed arm choices; no causal benefit of memory is identifiable.',
            'ranking_calls':0,'qrels_scoring_calls':0,'fits':0,'models':0}

def worker(root):
    # Limits apply only in this newly spawned interpreter, never the host session.
    import resource
    import signal
    for name in THREAD_ENV:
        os.environ[name] = '1'
    resource.setrlimit(resource.RLIMIT_CPU, (LIMITS['cpu_soft_seconds'], LIMITS['cpu_hard_seconds']))
    resource.setrlimit(resource.RLIMIT_AS, (LIMITS['address_space_bytes'], LIMITS['address_space_bytes']))
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITS['file_bytes'], LIMITS['file_bytes']))
    signal.alarm(LIMITS['wall_seconds'])
    freeze_raw, freeze = frozen(root)
    attempt = parse(read(root/'attempt.json'))
    require(attempt['freeze_sha256'] == sha(freeze_raw)
            and attempt['review_sha256'] == sha(read(root/'independent-review.json')),
            'Original approved attempt identity differs')
    reviewed(root,freeze_raw,freeze,read(root/'independent-review.json',65536))
    study_claim = parse(read(STUDY_CLAIM,65536))
    require(study_claim['study_id'] == STUDY_ID and study_claim['output_root'] == str(root.resolve())
            and study_claim['freeze_sha256'] == sha(freeze_raw)
            and study_claim['policy_sha256'] == freeze['policy_sha256']
            and study_claim['selection_sha256'] == freeze['selection_sha256']
            and study_claim['review_sha256'] == attempt['review_sha256'], 'Original study-wide execution claim differs')
    claim=root/'worker-claim.json'
    save(claim,{'freeze_sha256':sha(freeze_raw),'pid':os.getpid(),'automatic_retry':False})
    modules = runtime()
    retrieval, lexical, core, controller, workbench, registry = modules
    require(core.code_identity() == freeze['project_code_identity']
            and registry.runtime_dependencies() == freeze['runtime_dependencies'], 'Runtime identity changed')
    save(root/'host-start.json', {'disk': host.disk_headroom(root), 'limits': LIMITS,
                                 'python_executable': sys.executable, 'python_version': sys.version})
    from unittest.mock import patch
    import socket
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    from autoresearch import source_evidence_adapter
    guard_calls = {'ridge_fit': 0, 'scaler_fit': 0, 'network': 0, 'source_extraction': 0}
    guards = ExitStack()
    def forbidden(name):
        def fail(*args, **kwargs):
            guard_calls[name] += 1
            raise AssertionError('Forbidden native case operation: '+name)
        return fail
    for target, name in ((Ridge, 'ridge_fit'), (StandardScaler, 'scaler_fit')):
        guards.enter_context(patch.object(target, 'fit', side_effect=forbidden(name)))
    for target, attribute in ((socket.socket, 'connect'), (socket.socket, 'connect_ex'),
                              (socket.socket, 'sendto'), (socket, 'create_connection'), (socket, 'getaddrinfo')):
        guards.enter_context(patch.object(target, attribute, side_effect=forbidden('network')))
    guards.enter_context(patch.object(source_evidence_adapter, 'execute', side_effect=forbidden('source_extraction')))
    project = core.ResearchProject(root/'unmanaged-project')
    current = [project]
    (root/'steps').mkdir()
    def budget():
        return current[0].status()['budget'] if current[0].db.exists() else None
    def stage(name, command, body, function):
        before = budget()
        save(root/'steps'/ (name+'-request.json'), {'command': command, 'body': body,
                                                  'replay_body': body, 'budget_before': before,
                                                  'receiver_ref': {'project_root': str(current[0].root),
                                                                   'workbench_root': str(root/'manager') if command.startswith('LocalWorkbench.') else None},
                                                  'replay_policy': 'Never replay create into a vanished pre-import root; use exact original IDs only against the existing relocated DB.'})
        result = function()
        save(root/'steps'/ (name+'-result.json'), {'result': result, 'budget_after': budget()})
        return result
    try:
        body = {'source': str(root/'frozen/source.json'), 'goal': 'Independent ArguAna source-informed fixed lexical arm transfer with equal TF-IDF control; binary relevance and procedural public split, no causal memory or automatic promotion claim.',
                'budget_ref': freeze['budget_ref'], 'max_tool_calls': 2, 'method_id': METHOD}
        stage('01-create', 'ResearchProject.create', body, lambda: project.create(**body))
        cap = {'request_id': 'transfer-source-cap', 'expected_limit': 8, 'new_limit': 0,
               'expected_state_version': project.status()['state_version'], 'reason': 'No source extraction in this separately scoped native integration'}
        stage('02-source-cap', 'ResearchProject.limit_evidence_budget', cap, lambda: project.limit_evidence_budget(**cap))
        manager = workbench.LocalWorkbench(root/'manager')
        project_id = project.status()['id']
        intake = {'request_id': 'transfer-import', 'workspace': str(project.root)}
        def import_project():
            result = manager.import_project(**intake)
            current[0] = core.ResearchProject(result['workspace'])
            save(root/'project-relocation.json', {'project_id': project_id,
                                                'original_project_root': str(project.root),
                                                'relocated_project_root': result['workspace'],
                                                'import_request_id': intake['request_id'],
                                                'import_body': intake,
                                                'recovery_requires_existing_target_db': True,
                                                'create_at_original_root_after_import_forbidden': True})
            return result
        stage('03-import', 'LocalWorkbench.import_project', intake, import_project)
        select = {'request_id': 'transfer-select', 'project_id': project_id}
        stage('04-select', 'LocalWorkbench.select', select, lambda: manager.select(select))
        project, _ = manager.binding()
        current[0] = project
        plan = {'question': 'Does the frozen source-informed TF-IDF arm preserve coverage on independent ArguAna relative to BM25, with a structurally equal source-free TF-IDF control?',
                'basis': freeze['known_results']+' Policy sha256:'+freeze['policy_sha256']+' Source evidence: '+canonical(freeze['policy']['source_evidence']), 'steps': 'Run both frozen arms once as one primary action; inspect actual output; audit saved results; wait.',
                'expected_feedback': 'Keep complete results, adverse outcomes, source identity and zero fit/model/source budgets; no promotion.'}
        def save_plan(number, basis, steps):
            body = {'request_id': 'transfer-plan-'+str(number), 'project_id': project_id,
                    'expected_state_version': project.status()['state_version'],
                    'plan': {**plan, 'basis': basis, 'steps': steps}, 'reason': 'Actual observation-driven revision '+str(number)}
            return stage('plan'+str(number), 'LocalWorkbench.save_plan', body, lambda: manager.save_plan(body))
        def advance(name, method):
            context = controller.ProjectController(project.root).selection_context()
            save(root/'steps'/(name+'-context.json'), context)
            if method is None:
                choice = {'kind': 'wait'}
            else:
                matches = [c for c in context['candidates'] if c['method_id'] == method]
                require(len(matches) == 1, 'Expected one exact eligible native candidate')
                choice = {'kind': 'execute', 'candidate_id': matches[0]['id']}
            body = {'request_id': 'transfer-'+name, 'project_id': project_id,
                    'expected_state_version': context['state_version'], 'proposal': {
                        'schema_version': 'project-selection-proposal-v1', 'context_sha256': context['context_sha256'],
                        'provider': {'kind': 'operator_assistant', 'label': 'Predeclared host fixed pair; no model send'},
                        'choice': choice, 'rationale': 'Use this exact saved context and fixed method; preserve adverse results and scope.',
                        'evidence_citation_ids': []}}
            response = stage(name, 'LocalWorkbench.advance', body, lambda: manager.advance(body))
            require(response['status'] == 'completed' or method is None, 'Unknown/failed action; never replace or retry')
            with disabled(modules):
                old_budget = budget()
                replay = stage(name+'-replay', 'LocalWorkbench.advance', body, lambda: manager.advance(body))
                require(replay.get('replayed') and budget() == old_budget, 'Replay changed budget or was not recognized')
            return response
        save_plan(1, plan['basis'], plan['steps'])
        advance('primary', METHOD)
        primary = project.status()['actions'][0]
        artifact_raw = project._artifact(primary).read_bytes()
        envelope = parse(artifact_raw)
        require(envelope['sha256'] == primary['result_sha256']
                and sha(canonical({k: v for k, v in envelope.items() if k != 'sha256'}).encode()) == envelope['sha256'],
                'Actual primary result identity changed')
        actual = envelope['tool_result']
        feedback = {'action_id': primary['id'], 'result_sha256': primary['result_sha256'],
                    'observations': actual['observations'], 'paired_summary_sha256': sha(canonical(actual['result']['paired_summary']).encode()),
                    'adverse_count': len(actual['result'].get('adverse_queries', actual['result']['paired_summary'].get('adverse_cases', [])))}
        save(root/'actual-primary-feedback.json', feedback)
        with disabled(modules):
            save(root/'saved-policy-projection.json',policy_projection(actual,freeze['policy'],{'action_id':primary['id'],'result_sha256':primary['result_sha256']}))
        basis = 'Actual completed action '+primary['id']+' result sha256:'+primary['result_sha256']+'. Feedback sha256:'+sha(read(root/'actual-primary-feedback.json'))+'. Adverse count '+str(feedback['adverse_count'])+'. Inspect the saved evidence without a new solve/ranking or default promotion.'
        save_plan(2, basis, 'Saved-only arithmetic/identity/feasibility audit of this exact completed action; no new primary execution.')
        with disabled(modules):
            advance('audit', AUDIT)
        audit = project.status()['actions'][1]
        save_plan(3, 'Actual saved-only audit '+audit['id']+' result sha256:'+audit['result_sha256']+'. '+freeze['known_results'],
                  'Wait. Preserve both fixed arms, adverse results and all source/result identities; broader claims need a separately characterized task.')
        advance('wait', None)
        state = project.status()
        require(len(state['actions']) == 2 and state['research_status'] == 'waiting'
                and len(state['plan_revisions']) == 3, 'Unexpected final lifecycle')
        b = state['budget']
        require(b['local_tool_calls_used'] == 2 and b['local_tool_calls_reserved'] == 0
                and b['new_fits'] == 0 and b['fit_attempts_used'] == 0
                and b['new_model_requests'] == 0 and b['evidence_reads_used'] == 0, 'Budget mismatch')
        export = {'request_id': 'transfer-report', 'project_id': project_id, 'expected_state_version': state['state_version']}
        with disabled(modules):
            report = stage('report', 'LocalWorkbench.export', export, lambda: manager.export(export))
        require(not any(guard_calls.values()), 'A forbidden fit/network/source operation was attempted')
        after = protected()
        save(root/'protected-after.json', after)
        require(after == freeze['protected'], 'Original protected evidence changed')
        save(root/'final-project-status.json', project.status())
        save(root/'result.json', {'schema_version': 'g5-retrieval-transfer-result-v1', 'status': 'completed',
                                 'case':'independent_arguana_transfer','policy_sha256':freeze['policy_sha256'],'selection_sha256':freeze['selection_sha256'],
                                 'project_id': project_id, 'project_root': str(project.root),
                                 'freeze_sha256': sha(freeze_raw), 'budget': b, 'plan_revisions': 3,
                                 'research_status': 'waiting', 'report': report, 'protected_originals_equal': True,
                                 'known_results':freeze['known_results'],'automatic_promotion':False,'incremental_memory_benefit':0.0,
                                 'guard_call_counts': guard_calls,
                                 'api_calls': 0, 'development_token_currency_costs': None})
    except BaseException as error:
        if not (root/'protected-after.json').exists():
            save(root/'protected-after.json', protected())
        save(root/'worker-error.json', {'type': type(error).__name__, 'message': str(error),
                                       'budget': budget(), 'guard_call_counts': guard_calls,
                                       'automatic_retry': False})
        raise
    finally:
        guards.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_subparsers(dest='mode',required=True)
    prep=modes.add_parser('prepare')
    for name in ('output','packet','policy','selection'):
        prep.add_argument('--'+name,type=Path,required=True)
    prep.add_argument('--packet-sha256',required=True)
    prep.add_argument('--code-commit',required=True)
    execute=modes.add_parser('run')
    execute.add_argument('--output',type=Path,required=True)
    execute.add_argument('--review',type=Path,required=True)
    child=modes.add_parser('_worker',help=argparse.SUPPRESS)
    child.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.mode=='prepare':
        prepare(args)
    elif args.mode=='run':
        run(args)
    else:
        worker(args.output.absolute())


if __name__=='__main__':
    main()
